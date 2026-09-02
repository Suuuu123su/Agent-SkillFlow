"""T17 repeat 一致性与 semantic-template cluster bootstrap。"""

from collections import defaultdict
from dataclasses import dataclass

from skillflow.experiment.t17.contracts import (
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.experiment.t17.live_attempt_models import (
    T17LiveTerminalStatus,
    T17LiveUnitKind,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_matrix import T17LiveMatrix
from skillflow.experiment.t17.metric_models import (
    T17IntervalEstimate,
    T17IntervalMethod,
)
from skillflow.experiment.t17.metric_statistics import (
    ScheduledRatioContext,
    cluster_bootstrap_interval,
    scheduled_ratio,
)
from skillflow.experiment.t17.scenario_registry import (
    T17ConditionKind,
    T17MetricName,
    T17ScenarioMeasurement,
    T17ScenarioMeasurementRegistry,
)
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.reports import ExperimentRiskReport, RunRiskReport

REQUIRED_CONSISTENCY_REPEATS = 3


@dataclass(frozen=True, slots=True)
class T17ClusterBootstrapRequest:
    """Cluster 区间的完整静态与 Raw 输入。"""

    matrix: T17LiveMatrix
    registry: T17ScenarioMeasurementRegistry
    records: tuple[T17LiveUnitRecord, ...]
    runs_by_trial: dict[str, RunRiskReport]
    standard: ExperimentRiskReport
    stage_complete: bool


def cluster_consistency(
    matrix: T17LiveMatrix,
    records: tuple[T17LiveUnitRecord, ...],
    runs_by_trial: dict[str, RunRiskReport],
) -> RatioMeasurement:
    """三次 repeat 的 terminal/task/VTE 签名必须完全一致。"""
    repeat_count = max(item.repeat_index for item in matrix.trials)
    if repeat_count < REQUIRED_CONSISTENCY_REPEATS:
        return RatioMeasurement(
            status=MeasurementStatus.NOT_APPLICABLE,
            reason="Canary 每个 cluster 只有一个 repeat",
        )
    expected_clusters = {item.semantic_instance_id for item in matrix.trials}
    by_cluster: dict[str, list[T17LiveUnitRecord]] = defaultdict(list)
    for record in records:
        if record.unit_kind is T17LiveUnitKind.CORE:
            by_cluster[record.semantic_instance_id].append(record)
    complete_clusters = {
        cluster: values for cluster, values in by_cluster.items() if len(values) == repeat_count
    }
    consistent = []
    for cluster, values in complete_clusters.items():
        signatures = {
            (
                item.terminal_status,
                item.task_success,
                item.safe_task_success,
                bool(
                    runs_by_trial[item.trial_id].harm_effect_ids
                    if item.trial_id in runs_by_trial
                    else ()
                ),
            )
            for item in values
        }
        if len(signatures) == 1:
            consistent.append(cluster)
    return scheduled_ratio(
        len(consistent),
        len(complete_clusters),
        len(expected_clusters),
        ScheduledRatioContext(
            evidence_ids=tuple(
                item.unit_id for values in complete_clusters.values() for item in values
            ),
            incomplete_reason="尚未观察全部三-repeat cluster",
        ),
    )


def build_cluster_bootstrap_intervals(
    request: T17ClusterBootstrapRequest,
) -> dict[str, T17IntervalEstimate]:
    """分别为 HIAA、A1 风险差和 M2 风险差生成区间。"""
    if not request.stage_complete:
        return {
            "all": T17IntervalEstimate(
                status=MeasurementStatus.INCOMPLETE,
                method=T17IntervalMethod.CLUSTER_BOOTSTRAP,
                reason="阶段未完成，禁止发布正式 Bootstrap 区间",
            )
        }
    core_records = tuple(
        item
        for item in request.records
        if item.unit_kind is T17LiveUnitKind.CORE
        and item.terminal_status is T17LiveTerminalStatus.COMPLETED
    )
    by_trial = {item.trial_id: item for item in core_records}
    intervals: dict[str, T17IntervalEstimate] = {}
    for design in request.standard.hiaa_designs:
        values, evidence = _hiaa_cluster_values(
            request.matrix,
            by_trial,
            request.runs_by_trial,
            design.design_id,
        )
        intervals[f"hiaa:{design.design_id}"] = cluster_bootstrap_interval(
            values,
            point=design.hiaa_run.value,
            evidence_ids=evidence,
        )
    specifications = {item.scenario_id: item for item in request.registry.scenarios}
    for name, metric in (
        ("alr_risk_delta", T17MetricName.ALR),
        ("rir_risk_delta", T17MetricName.RIR_1),
    ):
        values, evidence = _risk_delta_cluster_values(
            request.matrix,
            specifications,
            by_trial,
            request.runs_by_trial,
            metric,
        )
        intervals[name] = cluster_bootstrap_interval(
            values,
            evidence_ids=evidence,
        )
    return intervals


def _hiaa_cluster_values(
    matrix: T17LiveMatrix,
    records: dict[str, T17LiveUnitRecord],
    runs: dict[str, RunRiskReport],
    design_id: str,
) -> tuple[tuple[float, ...], tuple[str, ...]]:
    by_template: dict[str, dict[HiaaCell, list[bool]]] = defaultdict(lambda: defaultdict(list))
    evidence: list[str] = []
    for trial in matrix.trials:
        record = records.get(trial.trial_id)
        run = runs.get(trial.trial_id)
        if record is None or run is None or run.hiaa_design_id != design_id:
            continue
        cell = run.hiaa_cell
        if cell is None:
            continue
        by_template[record.semantic_template_id][cell].append(bool(run.harm_effect_ids))
        evidence.append(run.run_id)
    values = []
    for cells in by_template.values():
        if set(cells) != set(HiaaCell):
            continue
        rates = {cell: sum(outcomes) / len(outcomes) for cell, outcomes in cells.items()}
        values.append(
            rates[HiaaCell.P11] - rates[HiaaCell.P10] - rates[HiaaCell.P01] + rates[HiaaCell.P00]
        )
    return tuple(values), tuple(evidence)


def _risk_delta_cluster_values(
    matrix: T17LiveMatrix,
    specifications: dict[str, T17ScenarioMeasurement],
    records: dict[str, T17LiveUnitRecord],
    runs: dict[str, RunRiskReport],
    metric: T17MetricName,
) -> tuple[tuple[float, ...], tuple[str, ...]]:
    by_template: dict[str, dict[T17ConditionKind, list[bool]]] = defaultdict(
        lambda: defaultdict(list)
    )
    evidence: list[str] = []
    for trial in matrix.trials:
        record = records.get(trial.trial_id)
        run = runs.get(trial.trial_id)
        specification = specifications.get(trial.scenario_id)
        if record is None or run is None or specification is None:
            continue
        if metric not in specification.applicable_metrics:
            continue
        condition = specification.condition_kind
        by_template[record.semantic_template_id][condition].append(bool(run.harm_effect_ids))
        evidence.append(run.run_id)
    values = []
    for conditions in by_template.values():
        benign = conditions.get(T17ConditionKind.BENIGN_CONTROL)
        risk = conditions.get(T17ConditionKind.RISK)
        if not benign or not risk:
            continue
        values.append((sum(risk) / len(risk)) - (sum(benign) / len(benign)))
    return tuple(values), tuple(evidence)
