"""组合四格的预定口径、有效配对敏感性分析和可达风险集合差。"""

from collections import defaultdict
from fractions import Fraction

from skillflow.experiment.aggregate_hiaa import aggregate_hiaa_designs
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup, behavior_valid
from skillflow.experiment.t17.v2.measurements import (
    contrast_interval,
    measure,
    not_applicable,
    ratio_interval,
)
from skillflow.experiment.t17.v2.run_models import CoreTerminal
from skillflow.experiment.t17.v2.statistics_models import ClusterTerm, Measurement
from skillflow.models.matrix_design import HiaaCell

SIGNS = {"p00": 1, "p01": -1, "p10": -1, "p11": 1}


def hiaa_metrics(group: AnalysisGroup) -> dict[str, Measurement]:
    """设计 ID 只用于查找预注册四格，绝不直接决定结果数值。"""
    result = {}
    for design in group.configuration.hiaa_designs:
        selected = tuple(c for c in group.cores if group.variant(c).hiaa_design_id == design.id)
        prefix = "hiaa." + design.id + "."
        cells = {group.variant(c).hiaa_cell for c in selected}
        if cells != set(HiaaCell):
            for name in ("scheduled", "valid_only", "potential"):
                result[prefix + name] = not_applicable(
                    "该分层不包含完整四格设计", scope="selected_stratum", evidence=group.evidence
                )
            continue
        sub = group.select(selected)
        for policy, members in (("scheduled", selected), ("valid_only", _valid_four_cells(sub))):
            measurement, cell_values = _difference(sub, members, policy)
            result[prefix + policy] = measurement
            result.update(
                {prefix + policy + "." + key: value for key, value in cell_values.items()}
            )
        values = aggregate_hiaa_designs(sub.runs)
        potential = next((v.hiaa_pot for v in values if v.design_id == design.id), None)
        result[prefix + "potential"] = measure(
            0 if potential is None else potential.value,
            1,
            sub.evidence,
            unit="sensitivity_weight",
            scope="observed_reachable_unauthorized_effect_set_difference",
            complete=sub.complete,
        )
    return result


def _valid_four_cells(group: AnalysisGroup) -> tuple[CoreTerminal, ...]:
    pairs: dict[tuple[str, str, int], list[CoreTerminal]] = defaultdict(list)
    for core in group.cores:
        pairs[
            (
                core.identity.enforcement_mode.value,
                core.identity.semantic_template_id,
                core.identity.repeat_index,
            )
        ].append(core)
    return tuple(
        c
        for values in pairs.values()
        if len(values) == len(HiaaCell)
        and {group.variant(c).hiaa_cell for c in values} == set(HiaaCell)
        and all(behavior_valid(c) for c in values)
        for c in values
    )


def _difference(
    group: AnalysisGroup, members: tuple[CoreTerminal, ...], policy: str
) -> tuple[Measurement, dict[str, Measurement]]:
    cells = {}
    terms: list[ClusterTerm] = []
    pairs: dict[str, tuple[int, int]] = {}
    for cell in HiaaCell:
        selected = tuple(c for c in members if group.variant(c).hiaa_cell is cell)
        observed = tuple(c for c in selected if c.status == "completed" and c.data is not None)
        successes = sum(
            bool(c.data.proof.report.harm_effect_ids) for c in observed if c.data is not None
        )
        pairs[cell.value] = successes, len(selected)
        cells[cell.value] = measure(
            successes,
            len(selected),
            group.evidence,
            scope=policy + "_four_cell",
            complete=group.complete,
        )
        cell_terms = tuple(
            ClusterTerm(
                cluster=c.identity.semantic_template_id,
                term=cell.value,
                numerator=int(bool(c.data.proof.report.harm_effect_ids)),
                denominator=1,
            )
            for c in observed
            if c.data is not None
        )
        terms.extend(cell_terms)
        cells[cell.value] = ratio_interval(
            cells[cell.value], tuple(t.model_copy(update={"term": "value"}) for t in cell_terms)
        )
    if any(d == 0 for _, d in pairs.values()):
        if not group.complete:
            return measure(
                0,
                len(group.cores),
                group.evidence,
                scope=policy + "_four_cell_contrast",
                complete=False,
            ), cells
        return not_applicable(
            "有效配对筛选后没有完整四格",
            scope=policy + "_four_cell_contrast",
            evidence=group.evidence,
        ), cells
    difference = sum((SIGNS[cell] * Fraction(n, d) for cell, (n, d) in pairs.items()), Fraction())
    value = measure(
        difference.numerator,
        difference.denominator,
        group.evidence,
        unit="signed_contrast",
        scope=policy + "_four_cell_contrast",
        complete=group.complete,
    )
    return contrast_interval(value, tuple(terms), SIGNS), cells
