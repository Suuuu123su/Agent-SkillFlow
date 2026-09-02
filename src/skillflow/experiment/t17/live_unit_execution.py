"""T17 Live 单个核心 Run 与成对 Replay 的受控执行。"""

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from skillflow.analysis.report_io import write_replay_risk_report
from skillflow.benchmark.replay import ReplayRunner, ReplayRunRequest
from skillflow.benchmark.replay_models import ReplayPairManifest
from skillflow.benchmark.runner import ScenarioRunner, ScenarioRunRequest
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.inputs import (
    apply_variant,
    namespace_grants,
    selected_harm_selector,
    slug,
)
from skillflow.experiment.io import sha256_file, write_json_model
from skillflow.experiment.layout import ExperimentLayout
from skillflow.experiment.matrix_support import ExecutedVariant, build_run_metadata
from skillflow.experiment.run_artifacts import require_mock_only
from skillflow.experiment.t17.live_attempt_models import T17ArtifactDigest
from skillflow.experiment.t17.live_matrix import T17LiveMatrix, T17LiveTrial
from skillflow.experiment.t17.observation_models import ReferenceObservationSnapshot
from skillflow.experiment.t17.observations import build_influence_observations
from skillflow.experiment.t17.reference_backend import ReferenceModelClient
from skillflow.experiment.t17.reference_harness import ReferenceHarnessFactory
from skillflow.experiment.t17.run_observer import T17RunObservationWriter
from skillflow.experiment.t17.scenario_registry import (
    T17ScenarioMeasurement,
    T17ScenarioMeasurementRegistry,
    expand_variant_measurements,
)
from skillflow.models.matrix import ExperimentMatrix, ExperimentVariant
from skillflow.models.references import ArtifactAliasRef
from skillflow.models.reports import ReplayRiskReport
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class T17LiveExecutionContext:
    """同一 Stage 的共享布局、冻结变体和 Reference Client。"""

    project_root: Path
    attempt_root: Path
    layout: ExperimentLayout
    experiment_id: str
    variants: dict[str, ExperimentVariant]
    specifications: dict[str, T17ScenarioMeasurement]
    observer: T17RunObservationWriter
    client: ReferenceModelClient


@dataclass(frozen=True, slots=True)
class T17LiveExecutionSetup:
    """创建 Stage 共享执行上下文的完整输入。"""

    project_root: Path
    attempt_root: Path
    layout: ExperimentLayout
    base_matrix: ExperimentMatrix
    live_matrix: T17LiveMatrix
    registry: T17ScenarioMeasurementRegistry
    client: ReferenceModelClient


@dataclass(frozen=True, slots=True)
class T17CoreExecution:
    """核心 Run 及其强 Task/Hook 观察。"""

    executed: ExecutedVariant
    snapshot: ReferenceObservationSnapshot
    safe_task_success: bool
    evidence_ids: tuple[str, ...]
    artifacts: tuple[T17ArtifactDigest, ...]


@dataclass(frozen=True, slots=True)
class T17ReplayExecution:
    """一个预注册目标的成对 Replay 与 Influence 观察。"""

    report: ReplayRiskReport
    evidence_ids: tuple[str, ...]
    artifacts: tuple[T17ArtifactDigest, ...]


def create_live_execution_context(
    setup: T17LiveExecutionSetup,
) -> T17LiveExecutionContext:
    """冻结 variant/spec 映射并创建 Stage 级观察写入器。"""
    base_specifications = {
        item.variant: item.scenario
        for item in expand_variant_measurements(setup.project_root, setup.registry)
    }
    specifications = {
        trial.variant: base_specifications[trial.source_variant]
        for trial in setup.live_matrix.trials
    }
    return T17LiveExecutionContext(
        project_root=setup.project_root,
        attempt_root=setup.attempt_root,
        layout=setup.layout,
        experiment_id=setup.attempt_root.name,
        variants={item.variant: item for item in setup.base_matrix.variants},
        specifications=specifications,
        observer=T17RunObservationWriter(
            setup.registry,
            setup.project_root,
            specifications,
        ),
        client=setup.client,
    )


def execute_live_core(
    context: T17LiveExecutionContext,
    trial: T17LiveTrial,
) -> T17CoreExecution:
    """执行一条真实模型核心 Trial，所有 Effect 仍进入 Safe Sink。"""
    variant = _variant(context, trial)
    scenario_path = context.project_root / trial.scenario.root
    run_id = f"run-{slug(trial.trial_id)}"
    scenario = namespace_grants(
        apply_variant(validate_yaml_document(scenario_path, Scenario), variant),
        run_id,
    )
    selector = variant.harm_selector or selected_harm_selector(scenario)
    scripts, decisions = t12_fixture_registry()
    runner = ScenarioRunner(
        scripts,
        decisions,
        ReferenceHarnessFactory(context.client, trial.task_prompt),
    )
    metadata = replace(
        build_run_metadata(
            context.experiment_id,
            variant,
            selector if variant.harm_selector is not None or scenario.harm_selector else None,
            redacted=True,
        ),
        backend="reference_harness",
    )
    result = runner.run_configured(
        ScenarioRunRequest(
            scenario_path=scenario_path,
            scenario=scenario,
            run_id=run_id,
            id_seed=f"{trial.trial_id}:{variant.seed}",
            layout=context.layout.run_layout(run_id),
            report_metadata=metadata,
        )
    )
    require_mock_only(result)
    executed = ExecutedVariant(variant, scenario_path, scenario, result)
    context.observer(executed)
    snapshot = context.observer.snapshots[-1]
    task = snapshot.task_success
    if task is None:
        raise T17LiveUnitExecutionError(trial.trial_id, "task_evidence_missing")
    specification = context.specifications[trial.variant]
    risk_executed = _risk_effect_executed(result.risk_report.effects, specification)
    evidence_ids = tuple(
        dict.fromkeys(
            (
                *task.evidence_ids,
                *(item.receipt_id for item in snapshot.effects if item.receipt_id is not None),
                *(value for hook in snapshot.hooks for value in hook.evidence_ids),
            )
        )
    )
    artifacts = _digests(
        context.attempt_root,
        (
            result.observed_trace_path,
            result.oracle_trace_path,
            result.security_graph_path,
            result.risk_report_path,
            result.risk_report_path.parent / "t17-observations.json",
        ),
    )
    return T17CoreExecution(
        executed=executed,
        snapshot=snapshot,
        safe_task_success=task.task_success and not risk_executed,
        evidence_ids=evidence_ids,
        artifacts=artifacts,
    )


def execute_live_replay(
    context: T17LiveExecutionContext,
    trial: T17LiveTrial,
    core: T17CoreExecution,
    target: ArtifactAliasRef,
) -> T17ReplayExecution:
    """从同一受控 Scenario 分叉 identity/neutral Replay pair。"""
    scripts, decisions = t12_fixture_registry()
    runner = ReplayRunner(
        scripts,
        decisions,
        ReferenceHarnessFactory(context.client, trial.task_prompt),
    )
    unit_id = replay_unit_id(trial, target)
    namespace = hashlib.sha256(unit_id.encode()).hexdigest()[:16]
    staging = context.layout.root / "blobs" / "r" / namespace
    batch = runner.run_configured(
        ReplayRunRequest(
            scenario_path=core.executed.scenario_path,
            scenario=core.executed.scenario,
            replay_root=staging,
            seed=f"{trial.trial_id}:{core.executed.variant.seed}:replay:{target.alias}",
            id_namespace=slug(unit_id),
            experiment_id=context.experiment_id,
            source_run_id=core.executed.result.run_id,
            scenario_ref=trial.scenario,
            redacted=True,
            target_alias=target.alias,
        )
    )
    if len(batch.pairs) != 1:
        raise T17LiveUnitExecutionError(unit_id, "replay_pair_count_invalid")
    pair = batch.pairs[0]
    destination = context.layout.root / "replays" / pair.report.replay_id
    destination.mkdir(parents=False, exist_ok=False)
    manifest = ReplayPairManifest.model_validate_json(
        pair.manifest_path.read_text(encoding="utf-8")
    )
    manifest_path = destination / "pair-manifest.json"
    report_path = destination / "replay-report.json"
    write_json_model(manifest_path, manifest)
    write_replay_risk_report(report_path, pair.report)
    influence = build_influence_observations((pair.report,))[0]
    return T17ReplayExecution(
        report=pair.report,
        evidence_ids=influence.evidence_ids,
        artifacts=_digests(context.attempt_root, (manifest_path, report_path)),
    )


def replay_unit_id(trial: T17LiveTrial, target: ArtifactAliasRef) -> str:
    """返回 Trial 与 counterfactual target 的唯一调度身份。"""
    return f"{trial.trial_id}--replay--{target.alias}"


class T17LiveUnitExecutionError(RuntimeError):
    """Live 单元没有产生预注册的强证据。"""

    __slots__ = ("detail", "identifier")

    def __init__(self, identifier: str, detail: str) -> None:
        """保存安全身份与 reason code，并保留 Exception 运行时状态。"""
        super().__init__(identifier, detail)
        self.identifier = identifier
        self.detail = detail

    def __str__(self) -> str:
        """返回不含正文的稳定诊断。"""
        return f"{self.identifier}:{self.detail}"


def _variant(
    context: T17LiveExecutionContext,
    trial: T17LiveTrial,
) -> ExperimentVariant:
    variant = context.variants.get(trial.source_variant)
    if variant is None or variant.scenario != trial.scenario:
        raise T17LiveUnitExecutionError(trial.trial_id, "variant_binding_invalid")
    return variant.model_copy(
        update={
            "variant": trial.variant,
            "enforcement_mode": trial.enforcement_mode,
        }
    )


def _risk_effect_executed(
    effects: tuple[object, ...],
    specification: T17ScenarioMeasurement,
) -> bool:
    aliases = {item.alias for item in specification.risk_effect_aliases}
    return any(
        getattr(item, "executed", False)
        and (
            getattr(item, "effect_alias", None) in aliases
            or bool(aliases.intersection(getattr(item, "selector_aliases", ())))
        )
        for item in effects
    )


def _digests(
    attempt_root: Path,
    paths: tuple[Path, ...],
) -> tuple[T17ArtifactDigest, ...]:
    return tuple(
        T17ArtifactDigest(
            relative_path=path.relative_to(attempt_root).as_posix(),
            sha256=sha256_file(path),
        )
        for path in paths
    )
