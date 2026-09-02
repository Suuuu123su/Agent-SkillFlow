"""从标准报告重建并验证 T17-D Scripted Golden。"""

import math
from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.io import sha256_file
from skillflow.experiment.report_store import read_risk_report
from skillflow.experiment.t17.contracts import (
    EvidenceDomain,
    EvidenceDomainKind,
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.experiment.t17.scenario_registry import (
    T17ScenarioMeasurement,
    T17ScenarioMeasurementRegistry,
    expand_variant_measurements,
)
from skillflow.experiment.t17.scripted_evidence import load_scripted_evidence
from skillflow.experiment.t17.scripted_models import (
    CausalImpactCounts,
    ScriptedFailureClassification,
    ScriptedGoldenSpecification,
    ScriptedGoldenStatus,
    ScriptedRunMeasurement,
    T17ScriptedGoldenSummary,
)
from skillflow.experiment.t17.scripted_provenance import (
    aggregate_scripted_provenance,
)
from skillflow.models.execution import ExperimentManifest
from skillflow.models.metrics import RatioMetric
from skillflow.models.reports import ExperimentRiskReport, ReplayRiskReport, RunRiskReport
from skillflow.models.run_results import RunEffectResult
from skillflow.validation import validate_yaml_document

__all__ = (
    "ScriptedGoldenStatus",
    "build_scripted_golden_summary",
    "load_scripted_golden_specification",
)


@dataclass(frozen=True, slots=True)
class ScriptedGoldenMismatchError(ValueError):
    """标准报告与独立 Golden 不一致。"""

    identifier: str
    detail: str

    def __str__(self) -> str:
        """返回稳定的 Golden 漂移诊断。"""
        return f"{self.identifier}:{self.detail}"


def load_scripted_golden_specification(path: Path) -> ScriptedGoldenSpecification:
    """读取独立于运行输出的 T17-D Golden。"""
    return validate_yaml_document(path, ScriptedGoldenSpecification)


def build_scripted_golden_summary(
    experiment_root: Path,
    registry: T17ScenarioMeasurementRegistry,
    golden: ScriptedGoldenSpecification,
) -> T17ScriptedGoldenSummary:
    """只读取标准报告并验证 24 core、18 Replay 与 5 次确定性。"""
    manifest_path = experiment_root / "experiment-manifest.json"
    report_path = experiment_root / "experiment-report.json"
    manifest = ExperimentManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    report = _experiment_report(report_path)
    runs = _run_reports(experiment_root)
    replays = _replay_reports(experiment_root)
    evidence_coverage = load_scripted_evidence(experiment_root, replays)
    specifications = {
        item.variant: item.scenario for item in expand_variant_measurements(Path(), registry)
    }
    measurements = tuple(_run_measurement(run, specifications[run.variant or ""]) for run in runs)
    _require_golden(manifest, report, measurements, replays, golden)
    task_successes = sum(item.task_success for item in measurements)
    safe_successes = sum(item.safe_task_success for item in measurements)
    target_effects = sum(item.verified_target_effect for item in measurements)
    hiaa = {item.design_id: item for item in report.hiaa_designs}
    causal = CausalImpactCounts(
        negative=sum(item.ci == -1 for item in replays),
        zero=sum(item.ci == 0 for item in replays),
        positive=sum(item.ci == 1 for item in replays),
    )
    type_keys = {key.model_dump_json() for run in runs for key in run.uea.canonical_effect_keys}
    evidence = tuple(item.run_id for item in runs)
    return T17ScriptedGoldenSummary(
        status=ScriptedGoldenStatus.PASSED,
        source_experiment_id=manifest.experiment_id,
        evidence_domain=EvidenceDomain(
            domain_id="t17-scripted-golden-v1",
            kind=EvidenceDomainKind.SCRIPTED,
            protocol_id="t17-scripted-v1",
            simulation_only=True,
            external_effects_simulated=True,
        ),
        observed_core_runs=len(runs),
        observed_replay_pairs=len(replays),
        determinism_passed=sum(item.consistent for item in manifest.determinism_checks),
        task_success_rate=_measured_ratio(task_successes, len(runs), evidence),
        safe_task_success_rate=_measured_ratio(safe_successes, len(runs), evidence),
        verified_target_effect_rate=_measured_ratio(target_effects, len(runs), evidence),
        task_success_evidence_coverage=evidence_coverage.task_success,
        receipt_coverage=evidence_coverage.receipts,
        hook_coverage=evidence_coverage.hooks,
        provenance=aggregate_scripted_provenance(runs),
        failures=ScriptedFailureClassification(
            reason=(
                "Scripted 域没有模型或 Provider 调用；失败分类不适用，不以数值 0 冒充真实模型结果"
            ),
        ),
        uea_count=report.raw_counts.unauthorized_executed_count,
        uea_type_count=len(type_keys),
        uea_weight=sum(run.uea.uea_weight for run in runs),
        hiaa_c1=_metric_value(hiaa["c1-context-grid"].hiaa_run.value, "c1"),
        hiaa_c2=_metric_value(hiaa["c2-tool-return-grid"].hiaa_run.value, "c2"),
        hiaa_potential_c1=hiaa["c1-context-grid"].hiaa_pot.value,
        hiaa_potential_c2=hiaa["c2-tool-return-grid"].hiaa_pot.value,
        alr=_legacy_ratio(report.alr),
        rir_1=_legacy_ratio(report.rir_1),
        rir_3=_legacy_ratio(report.rir_3),
        causal_impact=causal,
        experiment_manifest_sha256=sha256_file(manifest_path),
        experiment_report_sha256=sha256_file(report_path),
        runs=measurements,
    )


def _run_measurement(
    report: RunRiskReport,
    specification: T17ScenarioMeasurement,
) -> ScriptedRunMeasurement:
    if report.variant is None or report.task_success is None:
        raise ScriptedGoldenMismatchError(report.run_id, "run_identity_or_task_missing")
    risk_aliases = {item.alias for item in specification.risk_effect_aliases}
    target_aliases = risk_aliases | {item.alias for item in specification.legitimate_effect_aliases}
    risk_count = sum(_matches_alias(effect, risk_aliases) for effect in report.effects)
    target = any(_matches_alias(effect, target_aliases) for effect in report.effects)
    return ScriptedRunMeasurement(
        run_id=report.run_id,
        variant=report.variant,
        scenario_id=report.scenario_id,
        task_success=report.task_success,
        safe_task_success=report.task_success and risk_count == 0,
        verified_target_effect=target,
        risk_effect_count=risk_count,
        uea_count=report.uea.uea_count,
    )


def _matches_alias(effect: RunEffectResult, aliases: set[str]) -> bool:
    observed = set(effect.selector_aliases)
    if effect.effect_alias is not None:
        observed.add(effect.effect_alias)
    return bool(observed & aliases)


def _require_golden(
    manifest: ExperimentManifest,
    report: ExperimentRiskReport,
    runs: tuple[ScriptedRunMeasurement, ...],
    replays: tuple[ReplayRiskReport, ...],
    golden: ScriptedGoldenSpecification,
) -> None:
    if len(runs) != golden.expected_core_runs or len(replays) != golden.expected_replay_pairs:
        raise ScriptedGoldenMismatchError(golden.id, "run_or_replay_count")
    if len(manifest.determinism_checks) != golden.expected_core_runs or any(
        not item.consistent or item.repeats != golden.determinism_repeats
        for item in manifest.determinism_checks
    ):
        raise ScriptedGoldenMismatchError(golden.id, "determinism")
    expected = {item.variant: item for item in golden.runs}
    for run in runs:
        item = expected.get(run.variant)
        if item is None or (
            item.task_success,
            item.safe_task_success,
        ) != (run.task_success, run.safe_task_success):
            raise ScriptedGoldenMismatchError(run.variant, "task_or_safe_task")
    if report.raw_counts.unauthorized_executed_count != golden.uea_count:
        raise ScriptedGoldenMismatchError(golden.id, "uea_count")
    hiaa = {item.design_id: item for item in report.hiaa_designs}
    comparisons = (
        (_metric_value(hiaa["c1-context-grid"].hiaa_run.value, "c1"), golden.hiaa_c1),
        (_metric_value(hiaa["c2-tool-return-grid"].hiaa_run.value, "c2"), golden.hiaa_c2),
        (hiaa["c1-context-grid"].hiaa_pot.value, golden.hiaa_potential_c1),
        (hiaa["c2-tool-return-grid"].hiaa_pot.value, golden.hiaa_potential_c2),
    )
    if any(not math.isclose(actual, expected_value) for actual, expected_value in comparisons):
        raise ScriptedGoldenMismatchError(golden.id, "hiaa")
    counts = (
        (report.alr.numerator, report.alr.denominator),
        (report.rir_1.numerator, report.rir_1.denominator),
        (report.rir_3.numerator, report.rir_3.denominator),
    )
    expected_counts = (
        (golden.alr_numerator, golden.alr_denominator),
        (golden.rir_1_numerator, golden.rir_1_denominator),
        (golden.rir_3_numerator, golden.rir_3_denominator),
    )
    if counts != expected_counts:
        raise ScriptedGoldenMismatchError(golden.id, "alr_or_rir")
    if (
        sum(item.ci == 0 for item in replays) != golden.causal_impact_zero
        or sum(item.ci == 1 for item in replays) != golden.causal_impact_positive
    ):
        raise ScriptedGoldenMismatchError(golden.id, "causal_impact")


def _run_reports(root: Path) -> tuple[RunRiskReport, ...]:
    reports = tuple(
        read_risk_report(path / "run-report.json")
        for path in sorted((root / "runs").iterdir(), key=lambda item: item.name)
    )
    values = []
    for report in reports:
        match report:
            case RunRiskReport():
                values.append(report)
            case _:
                raise ScriptedGoldenMismatchError(root.name, "run_report_scope")
    return tuple(values)


def _replay_reports(root: Path) -> tuple[ReplayRiskReport, ...]:
    reports = tuple(
        read_risk_report(path / "replay-report.json")
        for path in sorted((root / "replays").iterdir(), key=lambda item: item.name)
    )
    values = []
    for report in reports:
        match report:
            case ReplayRiskReport():
                values.append(report)
            case _:
                raise ScriptedGoldenMismatchError(root.name, "replay_report_scope")
    return tuple(values)


def _experiment_report(path: Path) -> ExperimentRiskReport:
    report = read_risk_report(path)
    match report:
        case ExperimentRiskReport():
            return report
        case _:
            raise ScriptedGoldenMismatchError(path.name, "experiment_report_scope")


def _measured_ratio(
    numerator: int,
    denominator: int,
    evidence_ids: tuple[str, ...],
) -> RatioMeasurement:
    return RatioMeasurement(
        status=MeasurementStatus.MEASURED,
        numerator=numerator,
        denominator=denominator,
        scheduled_denominator=denominator,
        value=numerator / denominator,
        evidence_ids=evidence_ids,
    )


def _legacy_ratio(metric: RatioMetric) -> RatioMeasurement:
    if metric.value is None:
        raise ScriptedGoldenMismatchError("legacy-ratio", "not_measured")
    return _measured_ratio(metric.numerator, metric.denominator, metric.evidence_ids)


def _metric_value(value: float | None, identifier: str) -> float:
    if value is None:
        raise ScriptedGoldenMismatchError(identifier, "metric_not_measured")
    return value
