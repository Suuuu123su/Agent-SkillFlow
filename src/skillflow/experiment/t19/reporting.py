"""T19 九类指标的离线编排；读取逐链事实而非先前汇总值。"""

from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.measurements import measure
from skillflow.experiment.t17.v2.statistics_models import Measurement
from skillflow.experiment.t19.campaign import CampaignPlan
from skillflow.experiment.t19.causal_audit import CausalRow, audit_metrics, causal_row
from skillflow.experiment.t19.comparisons import PairedRow, comparison_metrics, paired_rows
from skillflow.experiment.t19.core_metrics import core_metrics
from skillflow.experiment.t19.diagnostics import diagnosis_metrics
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.experiment.t19.hiaa import hiaa_metrics
from skillflow.experiment.t19.matrix import GROUPS, Trial
from skillflow.experiment.t19.metric_adapter import MetricContext, adapt_core, adapt_replay
from skillflow.experiment.t19.public_facts import PublicCore, PublicReplay
from skillflow.experiment.t19.strict_metrics import alr_metrics, rir_metrics
from skillflow.models.base import StrictModel
from skillflow.models.enums import ArtifactType


class PublicIndex(StrictModel):
    """正式合同身份；没有原报告或已计算指标。"""

    phase_sha256: str
    plan: CampaignPlan
    tolerance_absolute: float = 1e-12
    tolerance_relative: float = 1e-12


class T19Report(StrictModel):
    """覆盖完整性与研究结论独立，质量验收由最终交付状态另外管理。"""

    data_status: str
    scheduled_core: int
    completed_core: int
    scheduled_audit: int
    terminal_audit: int
    metrics: dict[str, Measurement]
    paired: tuple[PairedRow, ...]
    causal: tuple[CausalRow, ...]
    statistical_scope: str = "两个独立任务模板；重复和Session不是独立簇，仅描述性配对，无总体区间"


def report(
    index: PublicIndex,
    public_cores: tuple[PublicCore, ...],
    public_replays: tuple[PublicReplay, ...],
) -> T19Report:
    """重建证明，然后才聚合；默认无网络入口。"""
    plan = index.plan
    cores = tuple(c.rebuild() for c in public_cores)
    records = {c.unit_id: c for c in cores}
    if len(records) != len(cores):
        raise ValueError("t19_duplicate_public_core")
    replays = tuple(r.rebuild() for r in public_replays)
    pairs = tuple(causal_row(r, p) for r, p in zip(replays, public_replays, strict=True))
    expected = tuple(
        t.trial_id + ":audit:" + a
        for t in plan.trials
        for a in plan.audit_aliases.get(t.trial_id, ())
    )
    complete = set(records) == {t.trial_id for t in plan.trials}
    replay_complete = {r.pair_id for r in replays} == set(expected) and len(replays) == len(
        expected
    )
    if any(c.trial not in plan.trials for c in public_cores):
        raise ValueError("t19_exported_trial_drift")
    metrics: dict[str, Measurement] = {}
    for label, trials in _strata(plan.trials).items():
        selected = tuple(records[t.trial_id] for t in trials if t.trial_id in records)
        metrics.update({label + "/" + k: v for k, v in core_metrics(trials, selected).items()})
        if label.startswith("main/"):
            metrics.update(
                {
                    label + "/diagnosis/" + k: v
                    for k, v in diagnosis_metrics(
                        selected, complete=len(selected) == len(trials)
                    ).items()
                }
            )
    metrics.update({"hiaa/" + k: v for k, v in hiaa_metrics(plan.trials, cores).items()})
    metrics.update({"audit/" + k: v for k, v in audit_metrics(expected, pairs).items()})
    context = MetricContext(index.phase_sha256, model_digest(plan))
    adapted = {
        c.trial.trial_id: adapt_core(context, c.trial, records[c.trial.trial_id], c.binding)
        for c in public_cores
    }
    adapted_pairs = tuple(adapt_replay(adapted[r.source_unit_id], r) for r in replays)
    common = _common_memory_blocks(
        plan.trials,
        records,
        {c.trial.trial_id: c.binding.source_control_hashes for c in public_cores},
    )
    for group in GROUPS:
        for mechanism, calculator in (("A1", alr_metrics), ("M2", rir_metrics)):
            if not any(t.group == group and t.mechanism == mechanism for t in plan.trials):
                continue
            strict_selected = tuple(
                adapted[t.trial_id]
                for t in plan.trials
                if t.group == group and t.mechanism == mechanism and t.trial_id in adapted
            )
            metrics.update(
                {
                    group + "/" + mechanism + "/" + k: v
                    for k, v in calculator(
                        strict_selected, adapted_pairs, complete=complete and replay_complete
                    ).items()
                }
            )
            if mechanism == "M2":
                subset = tuple(
                    adapted[t.trial_id]
                    for t in plan.trials
                    if t.group == group and t.mechanism == "M2" and t.block in common
                )
                if subset:
                    metrics.update(
                        {
                            group + "/M2/common/" + k: v
                            for k, v in rir_metrics(
                                subset, adapted_pairs, complete=complete and replay_complete
                            ).items()
                        }
                    )
                metrics[group + "/M2/common_eligible"] = measure(
                    len(subset),
                    len(strict_selected),
                    tuple(c.identity.unit_id for c in strict_selected),
                    complete=complete,
                    scope="all_six_groups_memory_write_and_revocation_observed",
                )
    paired = paired_rows(plan.trials, cores)
    metrics.update({"paired/" + k: v for k, v in comparison_metrics(plan.trials, paired).items()})
    return T19Report(
        data_status="complete" if complete and replay_complete else "incomplete",
        scheduled_core=len(plan.trials),
        completed_core=len(cores),
        scheduled_audit=len(expected),
        terminal_audit=len(replays),
        metrics=metrics,
        paired=paired,
        causal=pairs,
    )


def _strata(trials: tuple[Trial, ...]) -> dict[str, tuple[Trial, ...]]:
    result = {}
    for group in GROUPS:
        members = tuple(t for t in trials if t.group == group)
        if not members:
            continue
        result["main/" + group] = tuple(t for t in members if not t.supplementary)
        for key in sorted({(t.mechanism, t.template, t.role, str(t.bridge)) for t in members}):
            result["stratum/" + group + "/" + "/".join(key)] = tuple(
                t for t in members if (t.mechanism, t.template, t.role, str(t.bridge)) == key
            )
        for role in sorted({t.role for t in members}):
            result["role/" + group + "/" + role] = tuple(
                t for t in members if t.role == role and not t.supplementary
            )
    return {k: v for k, v in result.items() if v}


def _common_memory_blocks(
    trials: tuple[Trial, ...],
    records: dict[str, CoreRecord],
    control_hashes: dict[str, tuple[str, ...]],
) -> set[int]:
    result = set()
    for block in {t.block for t in trials if t.mechanism == "M2"}:
        members = tuple(t for t in trials if t.block == block)
        if len(members) == len(GROUPS) and all(
            t.trial_id in records
            and records[t.trial_id].data.proof.report.revocations
            and {1, 3}.issubset(records[t.trial_id].data.proof.report.rir_check_offsets)
            and any(
                a.artifact_type is ArtifactType.MEMORY
                and a.content_hash in control_hashes.get(t.trial_id, ())
                for a in records[t.trial_id].data.facts.artifacts
            )
            for t in members
        ):
            result.add(block)
    return result
