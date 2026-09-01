"""旧 v2 Model1 原始记录的只读聚类计数提取。"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.task_success_statistics import (
    ClusterRateCounts,
    PairedClusterCounts,
    bootstrap_hiaa_interval,
    wilson_interval,
)
from skillflow.experiment.t16.task_success_statistics_models import (
    ConditionWilsonEstimate,
    CountRate,
    HiaaAnalysis,
    HiaaCellEstimate,
)
from skillflow.experiment.t16.trial import TrialOutcome
from skillflow.models.matrix_design import HiaaCell

MODEL1_RECORD_COUNT = 360
CONDITION_RECORD_COUNT = 30
MODEL1_COUNT_ERROR = "Model1 必须精确包含360条唯一 Trial"
CONDITION_COUNT_ERROR = "12个条件必须各包含30条 Trial"
HIAA_CLUSTER_SHAPE_ERROR = "HIAA cluster 必须精确包含四格计数"
HIAA_CELLS = (HiaaCell.P00, HiaaCell.P01, HiaaCell.P10, HiaaCell.P11)
CONDITIONS = (
    "b0",
    "g0",
    "n0",
    "c1-p00",
    "c1-p01",
    "c1-p10",
    "c1-p11",
    "m2-control",
    "m2-target",
    "a1-claim",
    "a1-neutralized",
    "a2-structured-confirmation",
)


@dataclass(frozen=True, slots=True)
class ResamplingParameters:
    """部分重分析共享的 bootstrap 次数与固定种子。"""

    resamples: int
    seed: int


@dataclass(frozen=True, slots=True)
class PairedConditionQuery:
    """一个预注册 target-control 对及其机械 outcome。"""

    target_condition: str
    control_condition: str
    outcome: Callable[[LiveTrialRecord], bool]


@dataclass(frozen=True, slots=True)
class HiaaCellQuery:
    """一个语义实例、HIAA 格与分母策略。"""

    identity: str
    cell: HiaaCell
    valid_only: bool


def read_live_records(path: Path) -> tuple[LiveTrialRecord, ...]:
    """逐行严格解析旧 JSONL，不写入源文件。"""
    lines = tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)
    return tuple(LiveTrialRecord.model_validate_json(line) for line in lines)


def require_complete_model1(records: tuple[LiveTrialRecord, ...]) -> None:
    """锁定360条唯一链和每条件30条的历史边界。"""
    ids = tuple(item.result.trial_id for item in records)
    if len(records) != MODEL1_RECORD_COUNT or len(set(ids)) != MODEL1_RECORD_COUNT:
        raise ValueError(MODEL1_COUNT_ERROR)
    counts = {
        condition: sum(item.result.condition_id == condition for item in records)
        for condition in CONDITIONS
    }
    if set(counts.values()) != {CONDITION_RECORD_COUNT}:
        raise ValueError(CONDITION_COUNT_ERROR)


def hiaa_analysis(
    records: tuple[LiveTrialRecord, ...],
    valid_only: bool,
    resampling: ResamplingParameters,
) -> HiaaAnalysis:
    """按语义实例生成 scheduled 或 valid-only HIAA。"""
    members = tuple(item for item in records if item.hiaa_cell is not None)
    clusters = tuple(
        _hiaa_cluster(members, identity, valid_only)
        for identity in sorted({item.result.semantic_instance_id for item in members})
    )
    return HiaaAnalysis(
        denominator_policy="valid_only_sensitivity" if valid_only else "scheduled",
        cells=tuple(_hiaa_cell(members, cell, valid_only) for cell in HIAA_CELLS),
        hiaa=bootstrap_hiaa_interval(clusters, resampling.resamples, resampling.seed),
    )


def paired_clusters(
    records: tuple[LiveTrialRecord, ...],
    query: PairedConditionQuery,
) -> tuple[PairedClusterCounts, ...]:
    """保留同一语义实例内 target/control 的全部 repeat。"""
    selected = tuple(
        item
        for item in records
        if item.result.condition_id in {query.target_condition, query.control_condition}
    )
    return tuple(
        _paired_cluster(selected, identity, query)
        for identity in sorted({item.result.semantic_instance_id for item in selected})
    )


def condition_wilson(
    records: tuple[LiveTrialRecord, ...],
) -> tuple[ConditionWilsonEstimate, ...]:
    """计算12条件链级描述性 Wilson 95% CI。"""
    output: list[ConditionWilsonEstimate] = []
    for condition in CONDITIONS:
        selected = tuple(item for item in records if item.result.condition_id == condition)
        successes = sum(target_executed(item) for item in selected)
        output.append(
            ConditionWilsonEstimate(
                condition_id=condition,
                successes=successes,
                total=len(selected),
                value=successes / len(selected),
                interval=wilson_interval(successes, len(selected)),
                inference_note="descriptive_chain_level_not_cluster_adjusted",
            )
        )
    return tuple(output)


def target_executed(record: LiveTrialRecord) -> bool:
    """只从匹配 selector 的 accepted Tool audit 和 Receipt 判断执行。"""
    aliases = set(record.expected_target_effect_aliases)
    return any(
        call.accepted and call.receipt_id is not None and call.effect_alias in aliases
        for session in record.sessions
        for call in session.tool_calls
    )


def session_executed(record: LiveTrialRecord, session_index: int) -> bool:
    """从指定 Session 的平台 audit 判断匹配 Effect 是否带 Receipt。"""
    sessions = tuple(item for item in record.sessions if item.session_index == session_index)
    if len(sessions) != 1:
        detail = f"{record.result.trial_id}: 缺少唯一 Session {session_index}"
        raise ValueError(detail)
    session = sessions[0]
    aliases = set(session.expected_target_effect_aliases)
    return any(
        call.accepted and call.receipt_id is not None and call.effect_alias in aliases
        for call in session.tool_calls
    )


def _hiaa_cluster(
    records: tuple[LiveTrialRecord, ...],
    identity: str,
    valid_only: bool,
) -> ClusterRateCounts:
    counts = tuple(
        _cell_counts(
            records,
            HiaaCellQuery(identity=identity, cell=cell, valid_only=valid_only),
        )
        for cell in HIAA_CELLS
    )
    if len(counts) != len(HIAA_CELLS):
        raise ValueError(HIAA_CLUSTER_SHAPE_ERROR)
    successes = (counts[0][0], counts[1][0], counts[2][0], counts[3][0])
    totals = (counts[0][1], counts[1][1], counts[2][1], counts[3][1])
    return ClusterRateCounts(identity, successes, totals)


def _cell_counts(
    records: tuple[LiveTrialRecord, ...],
    query: HiaaCellQuery,
) -> tuple[int, int]:
    members = tuple(
        item
        for item in records
        if item.result.semantic_instance_id == query.identity and item.hiaa_cell is query.cell
    )
    selected = tuple(item for item in members if not query.valid_only or _is_valid(item))
    return sum(target_executed(item) for item in selected), len(selected)


def _hiaa_cell(
    records: tuple[LiveTrialRecord, ...],
    cell: HiaaCell,
    valid_only: bool,
) -> HiaaCellEstimate:
    selected = tuple(
        item for item in records if item.hiaa_cell is cell and (not valid_only or _is_valid(item))
    )
    successes = sum(target_executed(item) for item in selected)
    return HiaaCellEstimate(
        cell=cell,
        execution=CountRate(
            successes=successes,
            total=len(selected),
            value=successes / len(selected),
        ),
    )


def _paired_cluster(
    records: tuple[LiveTrialRecord, ...],
    identity: str,
    query: PairedConditionQuery,
) -> PairedClusterCounts:
    target = tuple(
        item
        for item in records
        if item.result.semantic_instance_id == identity
        and item.result.condition_id == query.target_condition
    )
    control = tuple(
        item
        for item in records
        if item.result.semantic_instance_id == identity
        and item.result.condition_id == query.control_condition
    )
    return PairedClusterCounts(
        identity,
        sum(query.outcome(item) for item in target),
        len(target),
        sum(query.outcome(item) for item in control),
        len(control),
    )


def _is_valid(record: LiveTrialRecord) -> bool:
    return target_executed(record) or record.result.outcome is not TrialOutcome.INVALID
