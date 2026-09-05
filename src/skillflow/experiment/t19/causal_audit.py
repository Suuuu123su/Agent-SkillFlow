"""事后重放差值、适用性和同视图波动，禁止提升为在线因果路由。"""

from skillflow.experiment.t17.v2.measurements import measure, not_applicable
from skillflow.experiment.t17.v2.replay_proof import _effect_ids
from skillflow.experiment.t17.v2.statistics_models import Measurement
from skillflow.experiment.t19.public_facts import PublicReplay
from skillflow.experiment.t19.replay import ReplayRecord
from skillflow.models.base import StrictModel


class CausalRow(StrictModel):
    """CI仅为操作性单次差值；同视图稳定也不足以证明总体因果。"""

    pair_id: str
    source_unit_id: str
    target_alias: str
    status: str
    reason: str
    ci: int | None
    y_original: bool | None
    y_neutral: bool | None
    y_same_view: bool | None
    behavior_valid: bool
    same_view_unstable: bool | None
    statistical_causality: str = "not_established_single_stochastic_pair"
    effect_ids: tuple[str, ...]


def causal_row(record: ReplayRecord, exported: PublicReplay) -> CausalRow:
    """使用回执效果判断每个分支，行为失败不会被隐去。"""
    p = record.proof
    same = (
        bool(_effect_ids(p.source, record.same_view, p.selector))
        if (p is not None and record.same_view is not None)
        else None
    )
    valid = len(exported.observations) == len(("identity", "neutral", "same_view")) and all(
        not b.issues
        and not b.limits
        and not b.boundary_issues
        and all(d.behavior == "normal" for d in b.decisions)
        for b in exported.observations
    )
    return CausalRow(
        pair_id=record.pair_id,
        source_unit_id=record.source_unit_id,
        target_alias=record.target_alias,
        status=record.status,
        reason=record.reason,
        ci=p.ci if p else None,
        y_original=p.y_original if p else None,
        y_neutral=p.y_neutral if p else None,
        y_same_view=same,
        behavior_valid=valid,
        same_view_unstable=same != p.y_original if p is not None and same is not None else None,
        effect_ids=(*p.original_effect_ids, *p.neutral_effect_ids) if p else (),
    )


def audit_metrics(expected: tuple[str, ...], rows: tuple[CausalRow, ...]) -> dict[str, Measurement]:
    """终态覆盖与数值适用性分开，缺补证不允许变为N/A。"""
    if not expected:
        return {"terminal_coverage": not_applicable("该阶段未调度重放")}
    complete = {r.pair_id for r in rows} == set(expected) and len(rows) == len(expected)
    valid = tuple(r for r in rows if r.ci is not None)
    result = {
        "terminal_coverage": measure(len(rows), len(expected), expected),
        "applicable": measure(len(valid), len(expected), expected, complete=complete),
        "same_view_unstable": measure(
            sum(r.same_view_unstable is True for r in valid),
            len(valid),
            expected,
            complete=complete,
        ),
        "behavior_valid": measure(
            sum(r.behavior_valid for r in valid), len(valid), expected, complete=complete
        ),
        "operational_influence_edges": measure(
            sum(len(r.effect_ids) for r in valid if r.ci != 0),
            1,
            expected,
            unit="edge_count",
            complete=complete,
        ),
    }
    for value in (-1, 0, 1):
        result["ci." + str(value)] = measure(
            sum(r.ci == value for r in valid), len(valid), expected, complete=complete
        )
    result["ci.mean"] = measure(
        sum(r.ci or 0 for r in valid),
        len(valid),
        expected,
        complete=complete,
        unit="signed_contrast",
    )
    return result
