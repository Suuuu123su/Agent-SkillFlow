"""从每个 core 的双轨 JSONL、SQLite 和 Blob 复算标准报告及正常任务。"""

from pathlib import Path

from pydantic import TypeAdapter

from skillflow.analysis.projection import RunTraceAnalysisInput, project_scenario_facts
from skillflow.analysis.reporting import analyze_scenario
from skillflow.benchmark.run_facts import load_effect_analysis_evidence, load_run_revocations
from skillflow.benchmark.success import TaskSuccessFacts, evaluate_task_success
from skillflow.experiment.inputs import apply_variant, namespace_grants
from skillflow.experiment.matrix_support import build_run_metadata
from skillflow.experiment.t17.contracts import HookName
from skillflow.experiment.t17.minimal.contracts import MinimalConfiguration
from skillflow.experiment.t17.minimal.raw_bindings import verify_record_bindings
from skillflow.experiment.t17.minimal.raw_validation import (
    read_jsonl,
    read_model,
    restore_run_receipts,
    verify_run_blobs,
)
from skillflow.experiment.t17.minimal.run_models import MinimalRunRecord
from skillflow.experiment.t17.minimal.task_evidence import TaskFacts, evaluate_task_facts
from skillflow.experiment.t17.minimal.task_models import NormalTaskEvidence
from skillflow.experiment.t17.observations import (
    ReferenceObservationRequest,
    build_reference_observations,
)
from skillflow.graph.models import SecurityGraphExport
from skillflow.graph.security import SecurityGraph
from skillflow.models.reports import RunRiskReport
from skillflow.models.scenario import Scenario
from skillflow.oracle.models import OracleTraceRecord
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.trace.observed import ObservedArtifactTrace, ObservedTraceRecord
from skillflow.validation import validate_yaml_document

_OBSERVED_ADAPTER: TypeAdapter[ObservedTraceRecord] = TypeAdapter(ObservedTraceRecord)
_ORACLE_ADAPTER: TypeAdapter[OracleTraceRecord] = TypeAdapter(OracleTraceRecord)


def verify_core_record(
    root: Path,
    record: MinimalRunRecord,
    configuration: MinimalConfiguration,
    project_root: Path,
) -> RunRiskReport:
    """报告必须等于同一 Raw 重新分析的结果；正常任务不得读取旧成功值。"""
    variant = next(item for item in configuration.matrix.variants if item.variant == record.variant)
    contract = next(
        item for item in configuration.tasks if item.scenario_path == variant.scenario.root
    )
    scenario = namespace_grants(
        apply_variant(
            validate_yaml_document(project_root / variant.scenario.root, Scenario), variant
        ),
        record.run_id,
    )
    directory = root / "runs" / record.run_id
    stored = read_model(directory / "run-report.json", RunRiskReport)
    observed = read_jsonl(directory / "observed-trace.jsonl", _OBSERVED_ADAPTER, "observed-trace")
    oracle = read_jsonl(directory / "oracle-trace.jsonl", _ORACLE_ADAPTER, "oracle-trace")
    aliases = {
        alias.removeprefix("artifact:"): item.artifact_id
        for item in observed
        if isinstance(item, ObservedArtifactTrace)
        for alias in item.aliases
        if alias.startswith("artifact:")
    }
    if aliases != record.artifact_ids_by_alias:
        raise ValueError("minimal_alias_trace_binding")
    with SqliteEventStore(root / "state.sqlite") as store:
        receipts = restore_run_receipts(store, root, record.run_id)
        verify_run_blobs(store, root, record.run_id)
        if tuple(item.receipt_artifact_id for item in receipts) != record.receipt_artifact_ids:
            raise ValueError("minimal_record_receipt_binding")
        artifacts = tuple(
            artifact
            for identifier in aliases.values()
            if (artifact := store.get_artifact(identifier)) is not None
        )
        legacy_success = evaluate_task_success(
            TaskSuccessFacts(
                scenario=scenario,
                artifact_ids_by_alias=aliases,
                artifacts=artifacts,
                effects=store.iter_run_effects(record.run_id),
                receipts=receipts,
            )
        )
        task = evaluate_task_facts(
            TaskFacts(
                record.run_id,
                scenario.id,
                aliases,
                receipts,
                legacy_success,
            ),
            contract,
            store,
        )
        if task != record.task or task != read_model(
            directory / "normal-task-evidence.json", NormalTaskEvidence
        ):
            raise ValueError("minimal_normal_task_recompute_mismatch")
        graph = SecurityGraph.from_store(store, record.run_id)
        if graph.to_export() != read_model(directory / "graph.json", SecurityGraphExport):
            raise ValueError("minimal_graph_recompute_mismatch")
        runtime = build_reference_observations(
            ReferenceObservationRequest(
                store=store,
                run_id=record.run_id,
                receipts=receipts,
                task_success_evidence=None,
                required_hooks=frozenset(contract.required_hooks) - {HookName.TASK_SUCCESS},
            )
        )
        if runtime != record.runtime:
            raise ValueError("minimal_runtime_observation_recompute_mismatch")
        verify_record_bindings(store, record, scenario)
        metadata = build_run_metadata(
            stored.experiment_id or "",
            variant,
            stored.harm_selector,
            redacted=True,
        )
        rebuilt = analyze_scenario(
            project_scenario_facts(
                RunTraceAnalysisInput(
                    scenario_id=scenario.id,
                    run_id=record.run_id,
                    observed_records=observed,
                    oracle_records=oracle,
                    graph=graph,
                    task_success=legacy_success,
                    scenario_definition=scenario,
                    metadata=metadata,
                    effect_evidence=load_effect_analysis_evidence(
                        store, store.iter_run_effects(record.run_id)
                    ),
                    runtime_artifacts=artifacts,
                    revocations=load_run_revocations(store, scenario, record.run_id),
                )
            )
        )
    if rebuilt != stored:
        raise ValueError("minimal_run_report_recompute_mismatch")
    return rebuilt
