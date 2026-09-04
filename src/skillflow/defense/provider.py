"""工具执行前附加防御；原授权、授权依据与执行回执不由防御重写。"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from time import perf_counter

from skillflow.defense.gates import CausalAttributionGate, TaskAlignmentGate, ToolDependencyGuard
from skillflow.defense.memory import DynamicRuleMemoryIsolator, QuarantineEntry
from skillflow.defense.models import AttackDiagnosis, AttackSignalVector, DefenseId, DefensePlan
from skillflow.defense.router import EvidenceDefenseRouter
from skillflow.defense.signals import SignalProjection, SignalProjectionRequest, project_signals
from skillflow.defense.task_plan import CausalAssessment, GateRequest, GateResult, TrustedTaskPlan
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import Decision, PrincipalType
from skillflow.models.scenario_parts import EffectSelector
from skillflow.policy.models import DecisionPlan
from skillflow.policy.runtime import PolicyToolRequest, StoredPolicyDecisionProvider
from skillflow.store.event_store import EventStore

ReplayCallback = Callable[[PolicyToolRequest, SignalProjection], CausalAssessment]


class DefenseTrace(StrictModel):
    """一次请求的实际判断链；最终操作事实另从事件库和回执提取。"""

    run_id: NonEmptyStr
    request_event_id: NonEmptyStr
    signals: AttackSignalVector
    diagnosis: AttackDiagnosis
    proposed_plan: DefensePlan
    selected: tuple[DefenseId, ...]
    gates: tuple[GateResult, ...]
    causal: CausalAssessment | None
    base_authorized: bool
    final_authorized: bool
    base_executed: bool
    final_executed: bool
    extra_steps: int
    latency_ms: float
    quarantine: tuple[QuarantineEntry, ...]


@dataclass(frozen=True, slots=True)
class Treatment:
    """固定组件或证据选择；运行器仅传组件配置，不传攻击标签。"""

    components: tuple[DefenseId, ...] = ()
    evidence_routing: bool = False


@dataclass(frozen=True, slots=True)
class DefenseSetup:
    """每个运行独立持有正常任务、风险选择器和可选隔离重放入口。"""

    run_id: str
    task_plan: TrustedTaskPlan
    selectors: tuple[EffectSelector, ...]
    treatment: Treatment
    replay: ReplayCallback | None = None


class DefendedDecisionProvider:
    """先取得原策略事实，再以拒绝/确认收紧执行；不能让被拒动作复活。"""

    def __init__(
        self, store: EventStore, base: StoredPolicyDecisionProvider, setup: DefenseSetup
    ) -> None:
        """状态仅属于本次 Run，不接收评分标签或场景标识。"""
        self._store, self._base, self._setup = store, base, setup
        self._memory = DynamicRuleMemoryIsolator()
        self.traces: list[DefenseTrace] = []

    def evaluate(self, request: PolicyToolRequest) -> DecisionPlan:
        """保持原授权原样，附加防御仅改变实际是否放行。"""
        start = perf_counter()
        base = self._base.evaluate(request)
        projection = project_signals(
            self._store,
            SignalProjectionRequest(
                self._setup.run_id,
                request,
                base,
                risk_target=self._risk(request),
            ),
        )
        diagnosis, proposed = EvidenceDefenseRouter().route(projection.signals)
        treatment = self._setup.treatment
        selected = (
            proposed.selected_defense_ids if treatment.evidence_routing else treatment.components
        )
        gate_request = GateRequest(
            request.effect,
            request.actor_id,
            request.boundary.session_id,
            self._setup.task_plan,
            projection.signals,
            self._completed(),
            authorized=base.authorized,
            base_executed=base.executed,
            memory_key=projection.memory_key,
            memory_operation=projection.memory_operation,
            memory_untrusted=projection.memory_untrusted,
            memory_artifact_ids=projection.memory_artifact_ids,
        )
        final = base
        gates: list[GateResult] = []
        causal = None
        if base.executed:
            if treatment.evidence_routing and proposed.action == "confirm":
                gates.append(
                    GateResult(
                        action="confirm",
                        reason="ROUTER_CONFIRMATION_REQUIRED",
                        evidence_ids=projection.signals.evidence_ids,
                    )
                )
            else:
                gates, causal = self._evaluate_components(
                    selected, gate_request, request, projection
                )
            blocked = next((g for g in gates if g.action != "allow"), None)
            if blocked is not None:
                final = replace(
                    base,
                    executed=False,
                    policy_result=Decision.CONFIRM
                    if blocked.action == "confirm"
                    else Decision.DENY,
                    reason_codes=(*base.reason_codes, blocked.reason),
                )
        self.traces.append(
            DefenseTrace(
                run_id=self._setup.run_id,
                request_event_id=projection.signals.request_event_id,
                signals=projection.signals,
                diagnosis=diagnosis,
                proposed_plan=proposed,
                selected=selected,
                gates=tuple(gates),
                causal=causal,
                base_authorized=base.authorized,
                final_authorized=final.authorized,
                base_executed=base.executed,
                final_executed=final.executed,
                extra_steps=sum(g.extra_steps for g in gates),
                latency_ms=(perf_counter() - start) * 1000,
                quarantine=self._memory.quarantine,
            )
        )
        return final

    def _evaluate_components(
        self,
        selected: tuple[DefenseId, ...],
        gate_request: GateRequest,
        request: PolicyToolRequest,
        projection: SignalProjection,
    ) -> tuple[list[GateResult], CausalAssessment | None]:
        gates = []
        causal = None
        for component in selected:
            if component == "task-alignment":
                result = TaskAlignmentGate().evaluate(gate_request)
            elif component == "tdg":
                result = ToolDependencyGuard().evaluate(gate_request)
            elif component == "drift-isolation":
                if not self._memory.rule_updates:
                    self._memory.update_rules(
                        PrincipalType.TRUSTED_POLICY,
                        self._setup.task_plan,
                        projection.prefix_events[0].event_id,
                    )
                result = self._memory.evaluate(gate_request)
            else:
                gate = CausalAttributionGate()
                causal = CausalAssessment(status="not_applicable", reason="no_high_risk_candidate")
                if gate.requires_replay(gate_request):
                    causal = (
                        self._setup.replay(request, projection)
                        if self._setup.replay is not None
                        else CausalAssessment(
                            status="not_available", reason="replay_callback_missing"
                        )
                    )
                result = gate.evaluate(gate_request, causal)
            gates.append(result)
            if result.action != "allow":
                break
        return gates, causal

    def _risk(self, request: PolicyToolRequest) -> bool:
        effect = request.effect
        return any(
            effect.action == s.action
            and effect.source == s.source_pattern
            and effect.sink == s.sink_pattern
            for s in self._setup.selectors
        )

    def _completed(self) -> frozenset[str]:
        completed: set[str] = set()
        for effect in self._store.iter_run_effects(self._setup.run_id):
            event = self._store.get_event(effect.request_event_id)
            if event is None or not effect.executed or effect.tool_receipt_id is None:
                continue
            node = next(
                (
                    n
                    for n in self._setup.task_plan.nodes
                    if n.node_id not in completed
                    and n.effect == effect.effect
                    and n.actor_id == event.actor_id
                    and n.session_id == event.session_id
                ),
                None,
            )
            if node is not None:
                completed.add(node.node_id)
        return frozenset(completed)
