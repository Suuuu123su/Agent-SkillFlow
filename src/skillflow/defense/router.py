"""预先冻结的证据路由；没有场景、技能路径或标签参数。"""

from skillflow.defense.models import (
    AttackDiagnosis,
    AttackSignalVector,
    DefenseAction,
    DefenseId,
    DefensePlan,
    Mechanism,
)

DEFENSE_ORDER: tuple[DefenseId, ...] = ("task-alignment", "tdg", "drift-isolation", "causal")
REQUIRED_EVIDENCE = ("authorization", "provenance")
HIGH_SEVERITY = 3
ROUTER_VERSION = "t18-evidence-rules/1.0"


class EvidenceDefenseRouter:
    """在任何留出技能运行前冻结的确定性最小并集规则。"""

    def route(self, signals: AttackSignalVector) -> tuple[AttackDiagnosis, DefensePlan]:
        """只读取信号字段；候选影响与已确认影响严格分开。"""
        mechanisms: list[Mechanism] = []
        selected: set[DefenseId] = set()
        reasons: list[str] = []
        action: DefenseAction = "allow"
        if signals.grant_missing or signals.scope_mismatch or signals.lifetime_mismatch:
            mechanisms.append("privilege")
            selected.update(("task-alignment", "drift-isolation"))
            reasons.append("AUTHORIZATION_BOUNDARY")
        if signals.untrusted_context_in_basis or signals.untrusted_tool_return_in_basis:
            mechanisms.append("context-tool")
            selected.add("tdg")
            reasons.append("UNTRUSTED_DECISION_INPUT")
            if signals.sink_severity >= HIGH_SEVERITY:
                selected.add("causal")
        if signals.cross_session_memory_path or signals.revoked_origin:
            mechanisms.append("memory")
            selected.add("drift-isolation")
            reasons.append("MEMORY_OR_REVOKED_PATH")
            if signals.target_effect_requested and signals.sink_severity >= HIGH_SEVERITY:
                selected.add("causal")
        if signals.authorization_claim_in_basis and signals.grant_missing:
            mechanisms.append("authorization")
            selected.add("task-alignment")
            reasons.append("UNTRUSTED_AUTHORIZATION_CLAIM")
            action = "confirm"
        missing = tuple(
            key for key in REQUIRED_EVIDENCE if not signals.evidence_availability.get(key, False)
        )
        if missing:
            reasons.append("REQUIRED_EVIDENCE_MISSING")
            if signals.sink_severity >= HIGH_SEVERITY:
                action = "confirm"
        if action == "allow" and "causal" in selected:
            action = "replay_then_decide"
        diagnosis = AttackDiagnosis(
            diagnosis_id="diagnosis:" + signals.request_event_id,
            mechanisms=tuple(mechanisms),
            confidence="low"
            if missing
            else ("medium" if mechanisms and not signals.confirmed_influence else "high"),
            abstain=bool(missing),
            evidence_ids=signals.evidence_ids,
            missing_evidence=missing,
        )
        return diagnosis, DefensePlan(
            plan_id="plan:" + signals.request_event_id,
            selected_defense_ids=tuple(item for item in DEFENSE_ORDER if item in selected),
            action=action,
            evidence_ids=signals.evidence_ids,
            selection_reason_codes=tuple(reasons),
            estimated_extra_steps=len(selected) + (2 if "causal" in selected else 0),
        )
