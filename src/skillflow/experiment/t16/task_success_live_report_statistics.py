"""T16-D.2 bridge 的 C1 与配对聚类统计。"""

from collections import defaultdict
from collections.abc import Callable

from skillflow.experiment.t16.task_success_live_models import T16D2RawTrialRecord
from skillflow.experiment.t16.task_success_live_report_models import (
    T16D2PairedEffectAnalysis,
)
from skillflow.experiment.t16.task_success_statistics import (
    BootstrapEstimate,
    ClusterRateCounts,
    PairedClusterCounts,
    bootstrap_hiaa_interval,
    bootstrap_paired_difference_interval,
)

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 16_162
MIN_CLUSTER_COUNT = 2


def c1_hiaa(
    records: tuple[T16D2RawTrialRecord, ...],
) -> BootstrapEstimate | None:
    """按语义实例聚类估计 C1 四格交互。"""
    cells = ("c1-p00", "c1-p01", "c1-p10", "c1-p11")
    clusters: dict[str, list[T16D2RawTrialRecord]] = defaultdict(list)
    for item in records:
        if item.live_trial.result.condition_id in cells:
            clusters[_template_id(item)].append(item)
    if len(clusters) < MIN_CLUSTER_COUNT:
        return None
    counts = []
    for cluster_id, items in sorted(clusters.items()):
        successes = _four_cell_successes(items, cells)
        totals = _four_cell_totals(items, cells)
        if any(total == 0 for total in totals):
            return None
        counts.append(ClusterRateCounts(cluster_id, successes, totals))
    return bootstrap_hiaa_interval(tuple(counts), BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED)


def m2_session(
    records: tuple[T16D2RawTrialRecord, ...],
    session_index: int,
) -> T16D2PairedEffectAnalysis | None:
    """计算指定 M2 Session 的 target-control 配对差。"""
    clusters: dict[str, list[T16D2RawTrialRecord]] = defaultdict(list)
    for item in records:
        if item.live_trial.result.condition_id in {"m2-target", "m2-control"}:
            clusters[_template_id(item)].append(item)
    return _paired_analysis(
        clusters,
        lambda item: _session_effect(item, session_index),
        "m2-target",
        "m2-control",
        BOOTSTRAP_SEED + session_index,
    )


def paired_conditions(
    records: tuple[T16D2RawTrialRecord, ...],
    target: str,
    control: str,
) -> T16D2PairedEffectAnalysis | None:
    """计算两个条件的语义实例聚类配对差。"""
    clusters: dict[str, list[T16D2RawTrialRecord]] = defaultdict(list)
    for item in records:
        if item.live_trial.result.condition_id in {target, control}:
            clusters[_template_id(item)].append(item)
    return _paired_analysis(
        clusters,
        lambda item: item.live_trial.result.target_effect_executed,
        target,
        control,
        BOOTSTRAP_SEED + 10,
    )


def _paired_analysis(
    clusters: dict[str, list[T16D2RawTrialRecord]],
    outcome: Callable[[T16D2RawTrialRecord], bool],
    target: str,
    control: str,
    seed: int,
) -> T16D2PairedEffectAnalysis | None:
    if len(clusters) < MIN_CLUSTER_COUNT:
        return None
    counts = []
    for cluster_id, items in sorted(clusters.items()):
        target_items = tuple(
            item for item in items if item.live_trial.result.condition_id == target
        )
        control_items = tuple(
            item for item in items if item.live_trial.result.condition_id == control
        )
        if not target_items or not control_items:
            return None
        counts.append(
            PairedClusterCounts(
                cluster_id,
                sum(outcome(item) for item in target_items),
                len(target_items),
                sum(outcome(item) for item in control_items),
                len(control_items),
            )
        )
    estimate = bootstrap_paired_difference_interval(
        tuple(counts),
        BOOTSTRAP_RESAMPLES,
        seed,
    )
    return T16D2PairedEffectAnalysis(
        target_successes=sum(item.target_successes for item in counts),
        target_total=sum(item.target_total for item in counts),
        control_successes=sum(item.control_successes for item in counts),
        control_total=sum(item.control_total for item in counts),
        estimate=estimate,
    )


def _session_effect(record: T16D2RawTrialRecord, session_index: int) -> bool:
    observation = next(
        (
            item
            for item in record.live_trial.session_observations
            if item.session_index == session_index
        ),
        None,
    )
    return observation.target_effect_executed if observation is not None else False


def _template_id(record: T16D2RawTrialRecord) -> str:
    return record.live_trial.result.semantic_instance_id.rsplit("-", 1)[-1]


def _cell_successes(items: list[T16D2RawTrialRecord], cell: str) -> int:
    return sum(
        item.live_trial.result.target_effect_executed
        for item in items
        if item.live_trial.result.condition_id == cell
    )


def _cell_total(items: list[T16D2RawTrialRecord], cell: str) -> int:
    return sum(item.live_trial.result.condition_id == cell for item in items)


def _four_cell_successes(
    items: list[T16D2RawTrialRecord],
    cells: tuple[str, str, str, str],
) -> tuple[int, int, int, int]:
    return (
        _cell_successes(items, cells[0]),
        _cell_successes(items, cells[1]),
        _cell_successes(items, cells[2]),
        _cell_successes(items, cells[3]),
    )


def _four_cell_totals(
    items: list[T16D2RawTrialRecord],
    cells: tuple[str, str, str, str],
) -> tuple[int, int, int, int]:
    return (
        _cell_total(items, cells[0]),
        _cell_total(items, cells[1]),
        _cell_total(items, cells[2]),
        _cell_total(items, cells[3]),
    )
