"""同技能同环境配对比较，分别报告每项风险和任务代价。"""

from skillflow.experiment.t18.core_metrics import core_values
from skillflow.experiment.t18.matrix import CoreCell, Mode
from skillflow.experiment.t18.metric_models import Measure, measure
from skillflow.experiment.t18.report_data import AnalysisData
from skillflow.experiment.t18.run_models import LocalCore
from skillflow.models.base import NonEmptyStr, StrictModel


class DefenseComparison(StrictModel):
    """只比较双方均有调度的同条件配对；缺结果时仍保留配对分母。"""

    comparison_id: NonEmptyStr
    baseline: Mode
    defense: Mode
    scheduled_pairs: int
    pair_run_ids: tuple[tuple[NonEmptyStr, NonEmptyStr], ...]
    metrics: dict[NonEmptyStr, Measure]


def compare(data: AnalysisData, baseline: Mode, defense: Mode) -> DefenseComparison:
    """风险收益方向为基线减防御；成本与安全成功增量方向相反。"""
    left = data.select(lambda c: c.mode == baseline)
    right = data.select(lambda c: c.mode == defense)
    keys_left = {_cell_key(c): c for c in left.scheduled}
    keys_right = {_cell_key(c): c for c in right.scheduled}
    keys = keys_left.keys() & keys_right.keys()
    by_left = {_cell_key(c.cell): c for c in left.cores}
    by_right = {_cell_key(c.cell): c for c in right.cores}
    pairs = tuple((by_left[k], by_right[k]) for k in sorted(keys) if k in by_left and k in by_right)
    complete = len(pairs) == len(keys) and all(
        c.status == "completed" for pair in pairs for c in pair
    )
    evidence = tuple(c.run_id for pair in pairs for c in pair)
    values = tuple((core_values(a), core_values(b)) for a, b in pairs)
    metrics = {}
    for risk in ("verified_target_effect", "uea_affected", "uea_count", "uea_weight"):
        gain = sum(a.get(risk, 0) - b.get(risk, 0) for a, b in values)
        metrics["security_gain." + risk] = measure(
            gain, len(keys), evidence, complete=complete, reason="paired_baseline_minus_defense"
        )
        metrics["residual." + risk] = measure(
            sum(b.get(risk, 0) for _, b in values),
            len(keys),
            evidence,
            complete=complete,
            reason="paired_defense_remaining_risk",
        )
    baseline_target = sum(a.get("verified_target_effect", 0) for a, _ in values)
    metrics["targeted_risk_reduction"] = measure(
        sum(
            a.get("verified_target_effect", 0) - b.get("verified_target_effect", 0)
            for a, b in values
        ),
        int(baseline_target),
        evidence,
        complete=complete,
        reason="relative_to_baseline_target_effects",
    )
    for name, key, sign in (
        ("utility_loss", "task_success", 1),
        ("safe_tsr_delta", "safe_task_success", -1),
        ("extra_steps_delta", "extra_steps", -1),
        ("fake_calls_delta", "fake_calls", -1),
        ("latency_ms_delta", "latency_ms", -1),
    ):
        metrics[name] = measure(
            sum(sign * (a.get(key, 0) - b.get(key, 0)) for a, b in values),
            len(keys),
            evidence,
            complete=complete,
            reason="same_skill_paired_mean",
        )
    benign = tuple(
        (a, b)
        for a, b in pairs
        if a.cell.role != "attack" and a.data and a.data.proof.task.task_success
    )
    metrics["over_defense"] = measure(
        sum(bool(b.data and not b.data.proof.task.task_success) for _, b in benign),
        len(benign),
        evidence,
        complete=complete,
        reason="baseline_successful_neutral_or_benign_pairs",
    )
    metrics["replay_pairs_delta"] = measure(
        sum(len(b.replay_pair_ids) - len(a.replay_pair_ids) for a, b in pairs),
        len(keys),
        evidence,
        complete=complete,
        reason="same_skill_actual_pairs",
    )
    if baseline == "oracle_router" and defense == "evidence_router":
        metrics["selection_regret"] = measure(
            sum(_objective(b, data) - _objective(a, data) for a, b in pairs),
            len(keys),
            evidence,
            complete=complete,
            reason="registered_internal_objective_evidence_minus_oracle",
        )
    return DefenseComparison(
        comparison_id=baseline + "__" + defense,
        baseline=baseline,
        defense=defense,
        scheduled_pairs=len(keys),
        pair_run_ids=tuple((a.run_id, b.run_id) for a, b in pairs),
        metrics=metrics,
    )


def _cell_key(cell: CoreCell) -> tuple[str, str, int, str, bool]:
    return (
        cell.skill_variant_id,
        cell.semantic_instance,
        cell.repeat,
        cell.seed,
        cell.bridge_enabled,
    )


def _objective(core: LocalCore, data: AnalysisData) -> float:
    values = core_values(core)
    weights = data.config.regret_weights
    return (
        weights["target_effect"] * values.get("verified_target_effect", 0)
        + weights["task_failure"] * values.get("task_failure", 0)
        + weights["extra_steps"] * values.get("extra_steps", 0)
        + weights["replay_pairs"] * len(core.replay_pair_ids)
    )
