"""预注册指标的逐层明细视图；不改变正式运行或原评分定义。"""

from collections import Counter
from decimal import Decimal

from skillflow.experiment.t16.provider import estimate_result_cost
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.measurements import measure, not_applicable
from skillflow.experiment.t17.v2.statistics_models import Measurement
from skillflow.experiment.t19.accounting import LedgerInputs
from skillflow.experiment.t19.core_metrics import core_metrics
from skillflow.experiment.t19.diagnostics import diagnosis_metrics
from skillflow.experiment.t19.metric_adapter import MetricContext, adapt_core, adapt_replay
from skillflow.experiment.t19.observations import coverage
from skillflow.experiment.t19.operational_views import operational_metrics
from skillflow.experiment.t19.public_facts import PublicCore, PublicReplay
from skillflow.experiment.t19.reporting import PublicIndex, _common_memory_blocks, _strata
from skillflow.experiment.t19.strict_metrics import alr_metrics, rir_metrics
from skillflow.models.base import StrictModel


class DetailReport(StrictModel):
    """原始费用项及预注册分层全部保留，不生成主观权重。"""

    metrics: dict[str, Measurement]
    recovery_costs: dict[str, str]
    usage_categories: dict[str, dict[str, str | int]]
    failure_event_counts: dict[str, int]
    common_memory_blocks: tuple[int, ...]
    metric_corrections: dict[str, str]


def details(
    index: PublicIndex,
    public: tuple[PublicCore, ...],
    pairs: tuple[PublicReplay, ...],
    ledger: LedgerInputs,
) -> DetailReport:
    """只从导出事实重新计算；不得读取原metrics数值。"""
    records = {p.trial.trial_id: p.rebuild() for p in public}
    context = MetricContext(index.phase_sha256, model_digest(index.plan))
    adapted = {
        p.trial.trial_id: adapt_core(context, p.trial, records[p.trial.trial_id], p.binding)
        for p in public
    }
    replays = tuple(p.rebuild() for p in pairs)
    adapted_pairs = tuple(adapt_replay(adapted[r.source_unit_id], r) for r in replays)
    common = _common_memory_blocks(
        index.plan.trials,
        records,
        {p.trial.trial_id: p.binding.source_control_hashes for p in public},
    )
    actual_pairs = {r.pair_id for r in replays}
    all_cores_present = set(records) == {t.trial_id for t in index.plan.trials}
    metrics = operational_metrics(index, records, ledger)
    corrections = {}
    strata = _strata(index.plan.trials)
    for label, trials in strata.items():
        chosen = tuple(records[t.trial_id] for t in trials if t.trial_id in records)
        complete = len(chosen) == len(trials)
        metrics.update({label + "/" + k: v for k, v in coverage(chosen, complete=complete).items()})
        corrections[label + "/required_step_observation_coverage"] = (
            "v1.1 counts actual trusted revoke/confirm/unload events; "
            "frozen-v1 counted only model steps"
        )
        metrics.update(
            {
                label + "/diagnosis/" + k: v
                for k, v in diagnosis_metrics(chosen, complete=complete).items()
            }
        )
        for mechanism, calculator in (("A1", alr_metrics), ("M2", rir_metrics)):
            selected = tuple(t for t in trials if t.mechanism == mechanism)
            if not selected:
                continue
            cores = tuple(adapted[t.trial_id] for t in selected if t.trial_id in adapted)
            audit_ids = {
                t.trial_id + ":audit:" + a
                for t in selected
                for a in index.plan.audit_aliases.get(t.trial_id, ())
            }
            closed = len(cores) == len(selected) and audit_ids.issubset(actual_pairs)
            metrics.update(
                {
                    label + "/" + mechanism + "/" + k: v
                    for k, v in calculator(cores, adapted_pairs, complete=closed).items()
                }
            )
            if mechanism == "M2":
                subset = tuple(adapted[t.trial_id] for t in selected if t.block in common)
                if subset:
                    metrics.update(
                        {
                            label + "/M2/common/" + k: v
                            for k, v in rir_metrics(subset, adapted_pairs, complete=closed).items()
                        }
                    )
                else:
                    for offset in (1, 3):
                        metrics[label + f"/M2/common/rir_{offset}"] = (
                            not_applicable(
                                "六组不存在共同的冻结控制内容写入与撤销观测集合",
                                evidence=tuple(t.trial_id for t in selected),
                                scope="all_six_groups_content_bound_pollution_set",
                            )
                            if all_cores_present
                            else measure(
                                0,
                                len(selected),
                                tuple(t.trial_id for t in selected),
                                complete=False,
                                scope="all_six_groups_content_bound_pollution_set",
                            )
                        )
    for group in {p.trial.group for p in public}:
        legal = tuple(
            t for t in index.plan.trials if t.group == group and t.mechanism in {"G0", "A2"}
        )
        if legal:
            metrics.update(
                {
                    "legal_sensitive/" + group + "/" + k: v
                    for k, v in core_metrics(
                        legal, tuple(records[t.trial_id] for t in legal if t.trial_id in records)
                    ).items()
                }
            )
            legal_cores = tuple(records[t.trial_id] for t in legal if t.trial_id in records)
            metrics.update(
                {
                    "legal_sensitive/" + group + "/" + k: v
                    for k, v in coverage(
                        legal_cores, complete=len(legal_cores) == len(legal)
                    ).items()
                }
            )
            corrections["legal_sensitive/" + group + "/required_step_observation_coverage"] = (
                "v1.1 counts actual trusted revoke/confirm/unload events; "
                "frozen-v1 counted only model steps"
            )
    recovery_costs, categories, failures = _usage_details(ledger)
    for failure in ("transport_failure", "http_error", "revision_drift"):
        events = tuple(e for rows in ledger.journals.values() for e in rows)
        evidence = tuple(e.event_sha256 for e in events)
        metrics["failure/" + failure] = measure(
            failures.get(failure, 0),
            sum(e.event_type == "attempt" for e in events),
            evidence,
            scope="all_T19_actual_API_attempts",
        )
    return DetailReport(
        metrics=metrics,
        recovery_costs=recovery_costs,
        usage_categories=categories,
        failure_event_counts=failures,
        common_memory_blocks=tuple(sorted(common)),
        metric_corrections=corrections,
    )


def _usage_details(
    ledger: LedgerInputs,
) -> tuple[dict[str, str], dict[str, dict[str, str | int]], dict[str, int]]:
    """重复CallIdentity已在导出前绑定真实阻断恢复证明，费用另由Token重算。"""
    recovery: dict[str, str] = {}
    categories: dict[str, dict[str, str | int]] = {}
    counts: Counter[str] = Counter()
    for name, events in ledger.journals.items():
        seen: Counter[tuple[str, str]] = Counter()
        for event in events:
            counts[event.event_type] += 1
            if event.event_type != "response" or event.usage is None:
                continue
            call = event.call.call_id if event.call else "missing"
            identity = (event.unit_id, call)
            seen[identity] += 1
            is_recovery = seen[identity] > 1
            cost = estimate_result_cost(ledger.pricing, event.usage)
            if is_recovery:
                recovery[name + ":" + str(event.attempt_index)] = str(cost)
            phase = (
                "formal"
                if name.startswith("formal")
                else "precheck"
                if name.startswith("precheck")
                else "technical"
            )
            kind = "audit" if ":audit:" in event.unit_id else "core"
            key = phase + "/" + kind + ("/recovery" if is_recovery else "/initial")
            bucket = categories.setdefault(key, {"responses": 0, "cost_usd": "0", "tokens": 0})
            bucket["responses"] = int(bucket["responses"]) + 1
            bucket["cost_usd"] = str(Decimal(str(bucket["cost_usd"])) + cost)
            bucket["tokens"] = (
                int(bucket["tokens"])
                + event.usage.input_tokens
                + event.usage.output_tokens
                + event.usage.reasoning_tokens
            )
    return recovery, categories, dict(counts)
