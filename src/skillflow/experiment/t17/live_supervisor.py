"""T17 Live 的单次秘密读取、阶段准备与跨阶段 Supervisor。"""

import getpass
import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import SecretStr

from skillflow.experiment.io import write_json_model
from skillflow.experiment.t16.httpx2_transport import managed_httpx2_transport
from skillflow.experiment.t16.openai_responses import OpenAIResponsesClient
from skillflow.experiment.t17.budget_proposal import T17BudgetProposal
from skillflow.experiment.t17.campaign_reporting import (
    T17CampaignReportingContext,
    update_campaign_reports,
)
from skillflow.experiment.t17.final_models import T17FinalMetricsReport
from skillflow.experiment.t17.live_matrix import (
    T17LiveStage,
    load_live_matrix,
    load_live_preregistration,
)
from skillflow.experiment.t17.live_preflight import (
    T17LivePreflightPaths,
    build_approved_live_config,
    build_budget_approval,
    build_live_preflight,
)
from skillflow.experiment.t17.live_reference_client import (
    OpenAIReferenceModelClient,
    T17ApprovedLiveConfig,
)
from skillflow.experiment.t17.live_stage import (
    T17LiveStageRequest,
    T17LiveStageResult,
    execute_live_stage,
)
from skillflow.experiment.t17.live_stage_support import T17LiveProgressSink
from skillflow.experiment.t17.metric_models import T17PhaseMetricsReport
from skillflow.experiment.t17.phase_report import (
    T17PhaseReportRequest,
    write_phase_metrics_report,
)

API_KEY_PROMPT = "请输入 OpenAI API Key（输入不可见，仅保存在当前 Supervisor 内存中）："
STAGE_MATRIX_FILENAMES = {
    T17LiveStage.CANARY: "matrix_canary.yaml",
    T17LiveStage.MODEL1: "matrix_model1.yaml",
    T17LiveStage.MODEL2_CANARY: "matrix_model2_canary.yaml",
    T17LiveStage.MODEL2: "matrix_model2.yaml",
    T17LiveStage.DEFENSE: "matrix_defense.yaml",
}


class T17SecretReader(Protocol):
    """允许测试替换不可见终端输入。"""

    def __call__(self, prompt: str) -> str:
        """读取一次秘密。"""
        ...


class T17PreparedStageExecutor(Protocol):
    """Supervisor 可替换的已批准阶段执行边界。"""

    def __call__(
        self,
        prepared: "T17PreparedLiveStage",
        api_key: SecretStr,
        progress: T17LiveProgressSink | None,
    ) -> T17LiveStageResult:
        """使用同一个内存 SecretStr 执行一阶段。"""
        ...


class T17BudgetConfirmation(Protocol):
    """当前精确预算提案经明确确认的边界。"""

    def __call__(self, proposal: T17BudgetProposal) -> bool:
        """确认当前已解析且已哈希的提案。"""
        ...


class T17PreparedStageReporter(Protocol):
    """Supervisor 可替换的阶段指标闭环。"""

    def __call__(
        self,
        prepared: "T17PreparedLiveStage",
        result: T17LiveStageResult,
    ) -> T17PhaseMetricsReport:
        """从已完成 Attempt 生成并返回完整 Phase 指标。"""
        ...


class T17EmptyApiKeyError(ValueError):
    """隐藏输入没有提供任何 API Key。"""

    def __str__(self) -> str:
        """返回不含秘密的稳定诊断。"""
        return "t17_api_key_empty"


@dataclass(frozen=True, slots=True)
class T17ConfirmedBudgetProposal:
    """确认时读取的精确 proposal 字节、模型和 SHA-256。"""

    source_path: Path
    proposal: T17BudgetProposal
    raw_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class T17PreparedLiveStage:
    """已写入 approval/preflight、尚未发送请求的阶段。"""

    stage: T17LiveStage
    attempt_root: Path
    proposal_path: Path
    proposal: T17BudgetProposal
    config: T17ApprovedLiveConfig
    request: T17LiveStageRequest


@dataclass(frozen=True, slots=True)
class T17SupervisorStageResult:
    """Supervisor 中一阶段的预算提案与执行结果。"""

    proposal_path: Path
    prepared: T17PreparedLiveStage
    result: T17LiveStageResult
    metrics: T17PhaseMetricsReport


def read_t17_api_key(reader: T17SecretReader | None = None) -> SecretStr:
    """只从不可见输入读取一次，不从环境变量或文件回退。"""
    raw = (reader or getpass.getpass)(API_KEY_PROMPT)
    if not raw:
        raise T17EmptyApiKeyError
    secret = SecretStr(raw)
    del raw
    return secret


def load_and_confirm_budget_proposal(
    proposal_path: Path,
    confirmation: T17BudgetConfirmation,
) -> T17ConfirmedBudgetProposal | None:
    """一次读取精确字节；确认对象与后续执行对象完全相同。"""
    source = proposal_path.resolve()
    raw = source.read_bytes()
    proposal = T17BudgetProposal.model_validate_json(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if not confirmation(proposal):
        return None
    return T17ConfirmedBudgetProposal(source, proposal, raw, digest)


def prepare_live_stage(
    project_root: Path,
    campaign_root: Path,
    confirmed: T17ConfirmedBudgetProposal,
    *,
    prepared_at: datetime | None = None,
) -> T17PreparedLiveStage:
    """在首次请求前独占创建 Attempt、批准记录与 preflight。"""
    root = project_root.resolve()
    t17_root = root / "experiments" / "t17"
    proposal = confirmed.proposal
    stage = proposal.stage
    matrix_path = t17_root / STAGE_MATRIX_FILENAMES[stage]
    preregistration_path = t17_root / "preregistration.yaml"
    registry_path = t17_root / "scenario_measurements.yaml"
    base_matrix_path = root / "scenarios" / "matrix" / "mvp.yaml"
    matrix = load_live_matrix(matrix_path)
    registration = load_live_preregistration(preregistration_path)
    timestamp = prepared_at or datetime.now(UTC)
    attempt_root = campaign_root / stage.value / "attempt-01"
    attempt_root.mkdir(parents=True, exist_ok=False)
    proposal_path = attempt_root / "budget-proposal.json"
    _write_confirmed_proposal(proposal_path, confirmed)
    approval = build_budget_approval(
        proposal_path,
        proposal,
        timestamp,
        proposal.requested_max_total_usd,
        proposal.requested_max_cost_per_run_usd,
    )
    approval_path = attempt_root / "budget-approval.json"
    write_json_model(approval_path, approval)
    config = build_approved_live_config(
        registration,
        matrix,
        proposal,
        approval,
    )
    preflight_inputs = T17LivePreflightPaths(
        project_root=root,
        preregistration_path=preregistration_path,
        matrix_path=matrix_path,
        registry_path=registry_path,
        base_matrix_path=base_matrix_path,
        proposal_path=proposal_path,
        approval_path=approval_path,
    )
    preflight = build_live_preflight(
        preflight_inputs,
        config,
        timestamp,
    )
    preflight_path = attempt_root / "preflight.json"
    write_json_model(preflight_path, preflight)
    return T17PreparedLiveStage(
        stage=stage,
        attempt_root=attempt_root,
        proposal_path=proposal_path,
        proposal=proposal,
        config=config,
        request=T17LiveStageRequest(
            project_root=root,
            attempt_root=attempt_root,
            matrix_path=matrix_path,
            base_matrix_path=base_matrix_path,
            registry_path=registry_path,
            preflight_path=preflight_path,
            preflight_inputs=preflight_inputs,
            config=config,
        ),
    )


def execute_prepared_live_stage(
    prepared: T17PreparedLiveStage,
    api_key: SecretStr,
    progress: T17LiveProgressSink | None,
) -> T17LiveStageResult:
    """展开 SecretStr 仅用于 OpenAI Client header，并执行一个阶段。"""
    with managed_httpx2_transport() as transport:
        provider_client = OpenAIResponsesClient(api_key, transport)
        reference_client = OpenAIReferenceModelClient(
            prepared.config,
            provider_client,
        )
        return execute_live_stage(
            prepared.request,
            reference_client,
            progress,
        )


def report_prepared_live_stage(
    prepared: T17PreparedLiveStage,
    _result: T17LiveStageResult,
) -> T17PhaseMetricsReport:
    """在 Raw SHA 复验后写出 Phase 指标报告。"""
    request = prepared.request
    return write_phase_metrics_report(
        T17PhaseReportRequest(
            attempt_root=prepared.attempt_root,
            matrix_path=request.matrix_path,
            registry_path=request.registry_path,
            base_matrix_path=request.base_matrix_path,
            output_path=prepared.attempt_root / "phase-metrics.json",
        )
    )


class T17LiveSupervisor:
    """同一进程内跨阶段复用一个 SecretStr，阶段间仅接收非秘密确认。"""

    def __init__(
        self,
        project_root: Path,
        campaign_root: Path,
        api_key: SecretStr,
        executor: T17PreparedStageExecutor = execute_prepared_live_stage,
        reporter: T17PreparedStageReporter | None = None,
    ) -> None:
        """绑定项目、全新 Campaign 根和唯一内存密钥。"""
        self._project_root = project_root.resolve()
        self._campaign_root = campaign_root.resolve()
        self._api_key = api_key
        self._executor = executor
        self._reporter = reporter or report_prepared_live_stage
        self._results: list[T17SupervisorStageResult] = []
        self._final_report: T17FinalMetricsReport | None = None

    @property
    def results(self) -> tuple[T17SupervisorStageResult, ...]:
        """返回当前 Supervisor 已完成的阶段。"""
        return tuple(self._results)

    @property
    def final_report(self) -> T17FinalMetricsReport | None:
        """Defense 完成后返回最终 Campaign 报告。"""
        return self._final_report

    def run_confirmed_stage(
        self,
        confirmed: T17ConfirmedBudgetProposal,
        progress: T17LiveProgressSink | None = None,
    ) -> T17SupervisorStageResult:
        """只接受与确认时精确字节绑定的 capability 对象。"""
        prepared = prepare_live_stage(
            self._project_root,
            self._campaign_root,
            confirmed,
        )
        result = self._executor(prepared, self._api_key, progress)
        metrics = self._reporter(prepared, result)
        stage_result = T17SupervisorStageResult(
            prepared.proposal_path,
            prepared,
            result,
            metrics,
        )
        self._results.append(stage_result)
        final_report = update_campaign_reports(
            T17CampaignReportingContext(
                self._project_root,
                self._campaign_root,
                tuple(self._results),
            ),
            stage_result,
        )
        if final_report is not None:
            self._final_report = final_report
        return stage_result


def _write_confirmed_proposal(
    path: Path,
    confirmed: T17ConfirmedBudgetProposal,
) -> None:
    """把确认的精确字节独占复制到 Attempt，并在返回前 fsync。"""
    if hashlib.sha256(confirmed.raw_bytes).hexdigest() != confirmed.sha256:
        raise T17ConfirmedProposalError
    try:
        with path.open("xb") as stream:
            stream.write(confirmed.raw_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise T17ConfirmedProposalError from error


class T17ConfirmedProposalError(RuntimeError):
    """确认字节或 Attempt 内副本无法保持一致。"""

    def __str__(self) -> str:
        """返回稳定 reason code。"""
        return "t17_confirmed_proposal_invalid"
