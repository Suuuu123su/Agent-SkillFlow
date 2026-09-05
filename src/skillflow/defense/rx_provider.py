"""T19 复用现有授权计算与请求事件，附加组件只收紧执行。"""

from dataclasses import dataclass, replace
from time import perf_counter

from skillflow.defense.rx import (
    ORDER,
    Component,
    Intervention,
    RequestEvidence,
    Selection,
    SourceEvidence,
    TaskConstraints,
    TreatmentName,
    intervene,
    select,
)
from skillflow.defense.signals import SignalProjectionRequest, project_signals
from skillflow.models.base import StrictModel
from skillflow.models.enums import ArtifactType, Decision
from skillflow.policy.models import DecisionPlan
from skillflow.policy.runtime import PolicyToolRequest, StoredPolicyDecisionProvider
from skillflow.store.event_store import EventStore


@dataclass(frozen=True, slots=True)
class RxSetup:
    """实验器只传组配置；没有场景、攻击目标或任务评测器。"""

    run_id: str
    task: TaskConstraints
    treatment: TreatmentName
    fixed: tuple[Component, ...] = ()


class RxTrace(StrictModel):
    """绑定实际请求，保留原授权与防御执行差异。"""

    evidence: RequestEvidence
    selection: Selection
    interventions: tuple[Intervention, ...]
    authorized_before: bool
    authorized_after: bool
    executed_before: bool
    executed_after: bool
    latency_ms: float
    authorization_ms: float | None = None
    projection_ms: float | None = None
    selection_ms: float | None = None
    intervention_ms: float | None = None


class RxDecisionProvider:
    """Monitor 保留研究基线；其余组共同使用纯授权底座 G。"""

    def __init__(
        self, store: EventStore, base: StoredPolicyDecisionProvider, setup: RxSetup
    ) -> None:
        """原策略必须配置为 Monitor；附加层不能把拒绝的基线变成执行。"""
        self._store, self._base, self._setup = store, base, setup
        self.traces: list[RxTrace] = []

    def evaluate(self, request: PolicyToolRequest) -> DecisionPlan:
        """执行前重新计算当时有效的 Grant、Scope、Lifetime 和撤销。"""
        start = perf_counter()
        base = self._base.evaluate(request)
        authorization_end = perf_counter()
        evidence = self._project(request, base)
        projection_end = perf_counter()
        setup = self._setup
        if setup.treatment in {"Evidence", "Coarse"}:
            selection = select(evidence, coarse=setup.treatment == "Coarse")
        else:
            components = (
                setup.fixed
                if setup.treatment == "Best Fixed"
                else ORDER
                if setup.treatment == "All"
                else ()
            )
            selection = Selection(
                components=components,
                abstain=not evidence.provenance_complete or not evidence.authorization_complete,
                reasons=("FIXED_COMPONENT_SET",),
                evidence_ids=evidence.evidence_ids,
            )
        selection_end = perf_counter()
        final = base
        results: tuple[Intervention, ...] = ()
        if setup.treatment != "Monitor" and base.executed:
            if not base.authorized:
                final = replace(
                    base,
                    executed=False,
                    policy_result=Decision.DENY,
                    reason_codes=(*base.reason_codes, "RX_GRANT_REQUIRED"),
                )
            else:
                results = intervene(selection, evidence)
                blocked = next((r for r in results if r.action != "allow"), None)
                if blocked is not None:
                    final = replace(
                        base,
                        executed=False,
                        policy_result=Decision.CONFIRM
                        if blocked.action == "confirm"
                        else Decision.DENY,
                        reason_codes=(*base.reason_codes, blocked.reason),
                    )
        intervention_end = perf_counter()
        self.traces.append(
            RxTrace(
                evidence=evidence,
                selection=selection,
                interventions=results,
                authorized_before=base.authorized,
                authorized_after=final.authorized,
                executed_before=base.executed,
                executed_after=final.executed,
                latency_ms=(intervention_end - start) * 1000,
                authorization_ms=(authorization_end - start) * 1000,
                projection_ms=(projection_end - authorization_end) * 1000,
                selection_ms=(selection_end - projection_end) * 1000,
                intervention_ms=(intervention_end - selection_end) * 1000,
            )
        )
        return final

    def _project(self, request: PolicyToolRequest, base: DecisionPlan) -> RequestEvidence:
        projection = project_signals(
            self._store,
            SignalProjectionRequest(self._setup.run_id, request, base, risk_target=False),
        )
        signals = projection.signals
        events = {e.event_id: e for e in projection.prefix_events}
        sources = []
        for identifier in projection.memory_artifact_ids:
            artifact = self._store.get_artifact(identifier)
            if artifact is None:
                raise ValueError("rx_missing_source")
            producer = events[artifact.created_by_event_id]
            channel = "skill"
            if artifact.artifact_type is ArtifactType.MEMORY:
                channel = "memory"
            elif artifact.artifact_type in {ArtifactType.TOOL_RETURN, ArtifactType.FILE}:
                channel = "tool"
            origins = set(artifact.observed_label.origins)
            revoked = bool(artifact.observed_label.revoked_origins) or any(
                r.event_id in events
                and r.target_kind.value == "principal"
                and r.target_id in origins | {producer.actor_id}
                for r in self._store.iter_run_revocations(self._setup.run_id)
            )
            sources.append(
                SourceEvidence.model_validate(
                    {
                        "artifact_id": identifier,
                        "producer_event_id": producer.event_id,
                        "channel": channel,
                        # Only the separate trusted task grants instruction authority.
                        "instruction_authority": False,
                        "revoked": revoked,
                        "memory_key": producer.metadata.get("memory_key")
                        if channel == "memory"
                        else None,
                        "memory_version_id": identifier if channel == "memory" else None,
                        "evidence_ids": (identifier, producer.event_id),
                    }
                )
            )
        return RequestEvidence(
            request_id=signals.request_event_id,
            actor_id=request.actor_id,
            session_id=request.boundary.session_id,
            effect=request.effect,
            grant_authorized=base.authorized,
            task_permitted=self._setup.task.permits(
                request.actor_id, request.boundary.session_id, request.effect
            ),
            sources=tuple(sources),
            provenance_complete=signals.evidence_availability.get("provenance", False),
            authorization_complete=base.manifest_id is not None,
            evidence_ids=signals.evidence_ids,
        )
