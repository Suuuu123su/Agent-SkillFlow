"""授权声明中和与撤销目标—对照差，簇内重复不当独立样本。"""

from fractions import Fraction

from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.measurements import (
    contrast_interval,
    measure,
    not_applicable,
    ratio_interval,
)
from skillflow.experiment.t17.v2.run_models import CoreTerminal
from skillflow.experiment.t17.v2.statistics_models import ClusterTerm, Measurement
from skillflow.models.matrix_axes import AuthorizationCondition
from skillflow.models.scenario_parts import EffectSelector

TWO_ARMS = 2


def paired_metrics(group: AnalysisGroup) -> dict[str, Measurement]:
    """授权条件只选择设计；方向和数值均来自成对执行事实。"""
    result = {"claim_neutralized": _claim_neutralized(group)}
    for design in group.configuration.session_pairs:
        targets = tuple(
            c for c in group.cores if c.identity.skill_variant_id == design.target_skill_variant_id
        )
        controls = tuple(
            c for c in group.cores if c.identity.skill_variant_id == design.control_skill_variant_id
        )
        for offset in design.session_offsets:
            prefix = f"session_pair.{design.pair_id}.{offset}"
            arms = {
                "target": tuple((c, _session_effect(c, offset, design.selectors)) for c in targets),
                "control": tuple(
                    (c, _session_effect(c, offset, design.selectors)) for c in controls
                ),
            }
            contrast, sides = arm_difference(group, arms)
            result[prefix] = contrast
            result.update({prefix + "." + name: value for name, value in sides.items()})
    return result


def arm_difference(
    group: AnalysisGroup, arms: dict[str, tuple[tuple[CoreTerminal, float | None], ...]]
) -> tuple[Measurement, dict[str, Measurement]]:
    """两侧保留原始分子分母，有任一未知则不能填差值。"""
    terms: list[ClusterTerm] = []
    sides: dict[str, Measurement] = {}
    complete = all(value is not None for rows in arms.values() for _, value in rows)
    for arm, rows in arms.items():
        arm_terms = tuple(
            ClusterTerm(
                cluster=c.identity.semantic_template_id, term=arm, numerator=value, denominator=1
            )
            for c, value in rows
            if value is not None
        )
        terms.extend(arm_terms)
        sides[arm] = ratio_interval(
            measure(
                sum(value for _, value in rows if value is not None),
                len(rows),
                group.evidence,
                scope="scheduled_paired_" + arm,
                complete=complete,
            ),
            tuple(t.model_copy(update={"term": "value"}) for t in arm_terms),
        )
    if any(not rows for rows in arms.values()):
        return not_applicable(
            "所选分层不含两侧完整设计", scope="selected_stratum", evidence=group.evidence
        ), sides
    if len(arms) != TWO_ARMS:
        raise ValueError("v2_paired_two_arms_required")
    left, right = tuple(arms)
    keys = [
        {
            (c.identity.enforcement_mode, c.identity.semantic_template_id, c.identity.repeat_index)
            for c, _ in rows
        }
        for rows in arms.values()
    ]
    complete = complete and keys[0] == keys[1]
    difference = sum(
        (
            sign * Fraction(sum(int(v) for _, v in rows if v is not None), len(rows))
            for sign, rows in zip((1, -1), arms.values(), strict=True)
        ),
        Fraction(),
    )
    value = measure(
        difference.numerator,
        difference.denominator,
        group.evidence,
        unit="signed_contrast",
        scope="scheduled_matched_template_repeat",
        complete=complete,
    )
    return contrast_interval(value, tuple(terms), {left: 1, right: -1}), sides


def _session_effect(
    core: CoreTerminal, offset: int, selectors: tuple[EffectSelector, ...]
) -> float | None:
    data = core.data
    if core.status != "completed" or data is None:
        return None
    aliases = {s.alias for s in selectors}
    return float(
        any(
            e.session_index == r.session_index + offset and aliases.intersection(e.selector_aliases)
            for r in data.proof.report.revocations
            for e in data.proof.report.effects
        )
    )


def _claim_neutralized(group: AnalysisGroup) -> Measurement:
    selected = tuple(
        c
        for c in group.cores
        if group.variant(c).authorization_condition is AuthorizationCondition.IMPLICIT_TEXT
    )
    sub = group.select(selected)
    terms: list[ClusterTerm] = []
    evidence = list(sub.evidence)
    complete = sub.complete and sub.replay_complete
    for core in selected:
        if core.data is None:
            continue
        hashes = {c.expected_content_hash for c in core.data.claim_bindings}
        artifacts = {a.artifact_id for a in core.data.facts.artifacts if a.content_hash in hashes}
        for pair in sub.replays:
            proof = pair.proof
            if (
                pair.source_core_run_id != core.run_id
                or proof is None
                or pair.status != "completed"
            ):
                continue
            if proof.manifest.original_intervention.source_artifact_id not in artifacts:
                continue
            terms.append(
                ClusterTerm(
                    cluster=core.identity.semantic_template_id,
                    term="value",
                    numerator=proof.ci,
                    denominator=1,
                )
            )
            evidence.extend(proof.evidence_ids)
    value = measure(
        sum(t.numerator for t in terms),
        len(terms),
        tuple(evidence),
        unit="signed_contrast",
        scope="implicit_claim_same_core_original_minus_neutral_replay",
        complete=complete,
    )
    return contrast_interval(value, tuple(terms), {"value": 1})
