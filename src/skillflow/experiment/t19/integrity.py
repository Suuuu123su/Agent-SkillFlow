"""交付完整性检查与研究数值分开，失败不能由低风险结果抵消。"""

from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.replay_proof import _validate_prefix
from skillflow.experiment.t19.accounting import LedgerInputs, recompute_cost
from skillflow.experiment.t19.observations import observations
from skillflow.experiment.t19.public_facts import PublicCore, PublicReplay
from skillflow.experiment.t19.reporting import PublicIndex
from skillflow.experiment.t19.source_certificates import SourceCertificates, validate_sources
from skillflow.models.base import StrictModel

MAX_STEPS = 16


class IntegrityReport(StrictModel):
    """绑定/预算/来源的逐项检查，不表示已通过项目全量质量门禁。"""

    status: str
    core_coverage: tuple[int, int]
    audit_coverage: tuple[int, int]
    checked_receipts: int
    checked_requests: int
    failures: tuple[str, ...]
    source_structure_scope: str = "private_content_observed_by_trusted_exporter_hash_bound_publicly"


def verify(
    index: PublicIndex,
    cores: tuple[PublicCore, ...],
    pairs: tuple[PublicReplay, ...],
    ledger: LedgerInputs,
    certificates: SourceCertificates,
) -> IntegrityReport:
    """独立读事实，核对每个单元及重放前缀在相同整链预算之内。"""
    failures = list(validate_sources(cores, pairs, certificates))
    expected = {t.trial_id for t in index.plan.trials}
    expected_pairs = {
        t.trial_id + ":audit:" + a
        for t in index.plan.trials
        for a in index.plan.audit_aliases.get(t.trial_id, ())
    }
    events = tuple(e for rows in ledger.journals.values() for e in rows)
    if {c.trial.trial_id for c in cores} != expected or len(cores) != len(expected):
        failures.append("core_schedule_incomplete_or_duplicate")
    if {p.rebuild().pair_id for p in pairs} != expected_pairs or len(pairs) != len(expected_pairs):
        failures.append("audit_schedule_incomplete_or_duplicate")
    checked_receipts = checked_requests = 0
    core_map = {c.trial.trial_id: c for c in cores}
    failures.extend(_check_cores(index, cores, events))
    failures.extend(_check_pairs(pairs, core_map, events))
    checked_receipts = sum(len(c.inputs.facts.receipts) for c in cores)
    checked_requests = sum(len(c.rebuild().traces) for c in cores)
    if not recompute_cost(ledger).complete:
        failures.append("unsettled_api_attempt")
    return IntegrityReport(
        status="passed" if not failures else "failed",
        core_coverage=(len(cores), len(expected)),
        audit_coverage=(len(pairs), len(expected_pairs)),
        checked_receipts=checked_receipts,
        checked_requests=checked_requests,
        failures=tuple(failures),
    )


def _check_cores(
    index: PublicIndex, cores: tuple[PublicCore, ...], events: tuple[ApiUsageEvent, ...]
) -> tuple[str, ...]:
    """核对实际请求、授权事实和模型用量绑定。"""
    failures = []
    for public in cores:
        core = public.rebuild()
        if any(not row.observed for row in observations(core)):
            failures.append(core.unit_id + ":required_step_observation_missing")
        attempts = tuple(
            e for e in events if e.unit_id == core.unit_id and e.event_type == "attempt"
        )
        responses = tuple(
            e for e in events if e.unit_id == core.unit_id and e.event_type == "response"
        )
        if core.domain == "live_reference" and (
            len(attempts) != core.usage.api_calls
            or len(responses) != core.usage.responses
            or len(attempts) > MAX_STEPS
            or len(core.decisions) > len(responses)
            or any(
                e.phase_contract_sha256 != index.phase_sha256
                or e.matrix_sha256 != model_digest(index.plan)
                for e in attempts
            )
        ):
            failures.append(core.unit_id + ":api_identity_or_budget_binding")
        if len(core.data.facts.effects) != len(core.data.facts.receipts):
            failures.append(core.unit_id + ":effect_without_receipt")
        order = {e.event_id: i for i, e in enumerate(core.data.facts.events)}
        for trace in core.traces:
            if trace.authorized_before != trace.authorized_after:
                failures.append(core.unit_id + ":authorization_fact_rewritten")
            request_order = order.get(trace.evidence.request_id, -1)
            if request_order < 0 or any(
                order.get(source.producer_event_id, len(order)) >= request_order
                for source in trace.evidence.sources
            ):
                failures.append(core.unit_id + ":source_after_request_or_missing")
    return tuple(failures)


def _check_pairs(
    pairs: tuple[PublicReplay, ...],
    core_map: dict[str, PublicCore],
    events: tuple[ApiUsageEvent, ...],
) -> tuple[str, ...]:
    """核对同源前缀与跨会话共享16步上限。"""
    failures = []
    for public in pairs:
        replay = public.rebuild()
        core = core_map.get(replay.source_unit_id)
        if core is None:
            continue
        if replay.proof is not None:
            p = replay.proof
            if p.source.events != core.inputs.facts.events[: len(p.source.events)]:
                failures.append(replay.pair_id + ":source_prefix_not_original_core")
            if replay.same_view is None:
                failures.append(replay.pair_id + ":same_view_missing")
            else:
                _validate_prefix(p.source, replay.same_view)
        for branch in ("identity", "neutral", "same_view"):
            attempts = tuple(
                e
                for e in events
                if e.unit_id == replay.pair_id + ":" + branch and e.event_type == "attempt"
            )
            if len(attempts) + replay.source_prefix_steps > MAX_STEPS:
                failures.append(replay.pair_id + ":" + branch + ":whole_chain_step_limit")
    return tuple(failures)
