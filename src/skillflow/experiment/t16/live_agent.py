"""T16-C 多 Session 编排与统一 Trial 分类。"""

import hashlib
import json
from dataclasses import dataclass

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent_calls import BudgetCheckpoint, LiveAgentClient
from skillflow.experiment.t16.live_agent_session import SessionRuntimeContext, execute_session
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.live_design_models import LiveTrialDesign
from skillflow.experiment.t16.live_record_builders import (
    LiveRecordEvidence,
    build_live_trial_record,
)
from skillflow.experiment.t16.live_records import LiveSessionRecord, LiveTrialRecord
from skillflow.experiment.t16.live_tools import LiveToolRuntime


@dataclass(frozen=True, slots=True)
class LiveTrialExecution:
    """一条 Trial 的结果与下一条可继续使用的保守预算状态。"""

    record: LiveTrialRecord
    budget: BudgetLedger


@dataclass(frozen=True, slots=True)
class LiveTrialExecutionOptions:
    """可选持久化 Hook 与阶段合同；单 Trial 单测可省略。"""

    budget_checkpoint: BudgetCheckpoint | None = None
    phase_contract_sha256: str | None = None


def execute_live_trial(
    design: LiveTrialDesign,
    config: T16CLiveConfig,
    client: LiveAgentClient,
    budget: BudgetLedger,
    options: LiveTrialExecutionOptions | None = None,
) -> LiveTrialExecution:
    """执行一条预注册 Trial；所有 Effect 都在本地 Receipt 运行时终止。"""
    options = options or LiveTrialExecutionOptions()
    runtime = LiveToolRuntime(
        run_nonce=design.matrix_trial_id,
        assets=design.assets,
        effect_alias_catalog={
            binding.public_alias: binding.actual_alias
            for session in design.sessions
            for binding in session.effect_alias_bindings
        },
    )
    current = budget
    context = SessionRuntimeContext(config, client, runtime, options.budget_checkpoint)
    sessions: list[LiveSessionRecord] = []
    retries: list[str] = []
    model_revision: str | None = None
    for session in design.sessions:
        runtime.activate_effect_aliases(session.allowed_effect_aliases)
        executed = execute_session(session, context, current)
        current = executed.budget
        record_payload = executed.record.model_dump(mode="python")
        record_payload["expected_target_effect_aliases"] = session.expected_target_effect_aliases
        session_record = LiveSessionRecord.model_validate(record_payload)
        sessions.append(session_record)
        retries.extend(executed.retry_events)
        model_revision = model_revision or executed.model_revision
        if _is_infrastructure_failure(session_record):
            break
    record = build_live_trial_record(
        design,
        config,
        tuple(sessions),
        LiveRecordEvidence(
            tuple(retries),
            model_revision,
            options.phase_contract_sha256 or _direct_execution_contract(config),
        ),
    )
    return LiveTrialExecution(record, current)


def _is_infrastructure_failure(record: LiveSessionRecord) -> bool:
    """只有 Provider/传输失败可以删失后续预注册观察 Session。"""
    return record.timeout or record.rate_limit or record.provider_error


def _direct_execution_contract(config: T16CLiveConfig) -> str:
    """为非 Phase 的单元执行生成可追踪合同；正式 Phase 会传入完整合同。"""
    payload = {
        "scope": "direct-live-trial",
        "config": config.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
