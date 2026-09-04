"""导出与重新计算共用的正常任务和风险证据链。"""

import hashlib
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter

from skillflow.analysis.facts import RunReportMetadata
from skillflow.analysis.projection import RunTraceAnalysisInput, project_scenario_facts
from skillflow.analysis.reporting import analyze_scenario
from skillflow.benchmark.run_facts import load_effect_analysis_evidence, load_run_revocations
from skillflow.benchmark.runner import ScenarioRunResult
from skillflow.experiment.t17.contracts import HookName
from skillflow.experiment.t17.minimal.contracts import NormalTaskContract
from skillflow.experiment.t17.minimal.task_evidence import (
    TaskFacts,
    evaluate_task_facts,
    validate_effect_receipts,
)
from skillflow.experiment.t17.observations import (
    ReferenceObservationRequest,
    build_reference_observations,
)
from skillflow.experiment.t17.v2.claim_models import ClaimActionSpec
from skillflow.experiment.t17.v2.fact_store import FactStore
from skillflow.experiment.t17.v2.hooks import measured_hooks
from skillflow.experiment.t17.v2.portable_models import (
    CoreProof,
    PortableCore,
    PortableCoreInputs,
    PortableRun,
)
from skillflow.graph.security import SecurityGraph
from skillflow.instrumentation.tool_receipt import ToolReceipt, ToolReceiptDraft, ToolReceiptIssuer
from skillflow.models.enums import EventType
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import TaskSpec
from skillflow.oracle.models import OracleTraceRecord
from skillflow.store.event_store import EventStore
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.trace.observed import ObservedTraceRecord

_DRAFT = TypeAdapter(ToolReceiptDraft)
RecordT = TypeVar("RecordT")


def capture_run(store: EventStore, run_id: str, receipts: tuple[ToolReceipt, ...]) -> PortableRun:
    """只读取实际事件库，收集所有元数据及原有回执 ID。"""
    events = store.iter_run_events(run_id)
    artifact_ids = tuple(dict.fromkeys(a for e in events for a in e.output_artifact_ids))
    artifacts = tuple(store.get_artifact(a) for a in artifact_ids)
    decisions = tuple(
        store.get_decision(e.decision_id) for e in events if e.decision_id is not None
    )
    if any(a is None for a in artifacts) or any(d is None for d in decisions):
        raise ValueError("v2_portable_facts_missing")
    return PortableRun(
        run_id=run_id,
        events=events,
        artifacts=tuple(a for a in artifacts if a is not None),
        decisions=tuple(d for d in decisions if d is not None),
        effects=store.iter_run_effects(run_id),
        grants=store.iter_run_grants(run_id),
        revocations=store.iter_run_revocations(run_id),
        receipts=tuple(_DRAFT.validate_json(r.to_bytes()) for r in receipts),
    )


def restore_receipts(facts: PortableRun, store: EventStore) -> tuple[ToolReceipt, ...]:
    """只恢复与原 Artifact 哈希匹配的原回执，不产生新操作。"""
    restored = []
    for draft in facts.receipts:
        artifact = store.get_artifact(draft.receipt_artifact_id)
        receipt = ToolReceiptIssuer().issue(draft)
        payload = receipt.to_bytes()
        if (
            artifact is None
            or hashlib.sha256(payload).hexdigest() != artifact.content_hash
            or len(payload) != artifact.content_length
        ):
            raise ValueError("v2_portable_receipt_content_binding")
        restored.append(receipt)
    result = tuple(restored)
    validate_effect_receipts(
        TaskFacts(facts.run_id, "portable", {}, result, None), facts.effects, store
    )
    return result


def capture_core(
    result: ScenarioRunResult,
    scenario: Scenario,
    contract: NormalTaskContract,
    metadata: RunReportMetadata,
    claims: tuple[ClaimActionSpec, ...] = (),
) -> PortableCore:
    """去除提示、资产正文和宿主路径，计算一份独立证明。"""
    with SqliteEventStore(result.database_path) as store:
        facts = capture_run(store, result.run_id, result.receipts)
    inputs = PortableCoreInputs(
        facts=facts,
        analysis_definition=redact_definition(scenario),
        task_contract=contract,
        metadata=metadata,
        artifact_ids_by_alias=result.artifact_ids_by_alias,
        observed=_lines(result.observed_trace_path, TypeAdapter(ObservedTraceRecord)),
        oracle=_lines(result.oracle_trace_path, TypeAdapter(OracleTraceRecord)),
        claim_bindings=claims,
    )
    return PortableCore(**inputs.model_dump(), proof=recompute_core(inputs))


def recompute_core(core: PortableCoreInputs) -> CoreProof:
    """不用数据库、Blob、模型正文或先前报告，从结构化事实复算全部单运行结果。"""
    store = FactStore(core.facts)
    scenario = core.analysis_definition
    run_id = core.facts.run_id
    receipts = restore_receipts(core.facts, store)
    task = evaluate_task_facts(
        TaskFacts(run_id, scenario.id, core.artifact_ids_by_alias, receipts, None),
        core.task_contract,
        store,
    )
    runtime = build_reference_observations(
        ReferenceObservationRequest(
            store,
            run_id,
            receipts,
            None,
            frozenset(core.task_contract.required_hooks) - {HookName.TASK_SUCCESS},
        )
    )
    hooks = measured_hooks(runtime, task, core.facts.events)
    runtime = runtime.model_copy(update={"hooks": tuple(h for h in hooks)})
    artifacts = tuple(store.get_artifact(a) for a in core.artifact_ids_by_alias.values())
    if any(a is None for a in artifacts):
        raise ValueError("v2_portable_alias_binding")
    report = analyze_scenario(
        project_scenario_facts(
            RunTraceAnalysisInput(
                scenario_id=scenario.id,
                run_id=run_id,
                observed_records=core.observed,
                oracle_records=core.oracle,
                graph=SecurityGraph.from_store(store, run_id),
                task_success=task.task_success,
                scenario_definition=scenario,
                metadata=core.metadata,
                effect_evidence=load_effect_analysis_evidence(store, core.facts.effects),
                runtime_artifacts=tuple(a for a in artifacts if a is not None),
                revocations=load_run_revocations(store, scenario, run_id),
                allow_absent_counterfactuals=True,
            )
        )
    )
    return CoreProof(
        task=task,
        runtime=runtime,
        hooks=hooks,
        report=report,
        step_event_ids=tuple(
            e.event_id for e in core.facts.events if e.event_type is EventType.SKILL_INVOKE
        ),
    )


def redact_definition(scenario: Scenario) -> Scenario:
    """保留来源声明、选择器和会话结构；移除自然语言提示及输入正文。"""
    value = scenario.model_copy(
        update={
            "description": "用于复算的结构化定义，禁止据此续跑实验。",
            "task": TaskSpec(id=scenario.task.id, prompt="提示正文未导出。"),
            "assets": tuple(a.model_copy(update={"marker": None}) for a in scenario.assets),
        }
    )
    return Scenario.model_validate(value.model_dump())


def _lines(path: Path, adapter: TypeAdapter[RecordT]) -> tuple[RecordT, ...]:
    return tuple(
        adapter.validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
