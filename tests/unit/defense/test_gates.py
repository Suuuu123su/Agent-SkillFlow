from dataclasses import replace

import pytest
from pydantic import ValidationError

from skillflow.defense.gates import CausalAttributionGate, TaskAlignmentGate, ToolDependencyGuard
from skillflow.defense.memory import DynamicRuleMemoryIsolator
from skillflow.defense.models import AttackSignalVector
from skillflow.defense.task_plan import CausalAssessment, GateRequest, TaskNode, TrustedTaskPlan
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import PrincipalType


def request() -> GateRequest:
    effect = CapabilityEffect.model_validate(
        {
            "source": "workspace:/input.txt",
            "sink": "context:/task",
            "action": "file.read",
            "scope": "exact-file",
            "lifetime": "call",
            "sensitivity": 1,
        }
    )
    signals = AttackSignalVector.model_validate(
        {
            "run_id": "r",
            "session_id": "s",
            "request_event_id": "request",
            **dict.fromkeys(
                (
                    "grant_missing",
                    "scope_mismatch",
                    "lifetime_mismatch",
                    "revoked_origin",
                    "untrusted_context_in_basis",
                    "untrusted_tool_return_in_basis",
                    "cross_session_memory_path",
                    "authorization_claim_in_basis",
                    "candidate_influence",
                    "confirmed_influence",
                    "target_effect_executed",
                    "receipt_present",
                ),
                False,
            ),
            "target_effect_requested": True,
            "sink_severity": 1,
            "evidence_availability": {"authorization": True, "provenance": True},
            "evidence_ids": ["request"],
            "signal_evidence": {},
        }
    )
    node = TaskNode(
        node_id="n",
        actor_id="a",
        session_id="s",
        effect=effect,
        predecessor_ids=(),
        parameter_schema_id="read_file",
    )
    return GateRequest(
        effect,
        "a",
        "s",
        TrustedTaskPlan(plan_id="task", nodes=(node,)),
        signals,
        frozenset(),
        authorized=True,
        base_executed=True,
    )


def test_alignment_valid_and_wrong_resource() -> None:
    item = request()
    assert TaskAlignmentGate().evaluate(item).action == "allow"
    wrong = item.effect.model_copy(update={"sensitivity": 4})
    assert TaskAlignmentGate().evaluate(replace(item, effect=wrong)).action == "deny"
    assert TaskAlignmentGate().evaluate(replace(item, authorized=False)).action == "confirm"


def test_dependency_checks_predecessor_and_repeated_step() -> None:
    item = request()
    prerequisite = item.task_plan.nodes[0].model_copy(update={"node_id": "previous"})
    node = item.task_plan.nodes[0].model_copy(update={"predecessor_ids": ("previous",)})
    plan = TrustedTaskPlan(plan_id="task", nodes=(prerequisite, node))
    gated = replace(item, task_plan=plan, completed_node_ids=frozenset({"previous"}))
    assert ToolDependencyGuard().evaluate(gated).action == "allow"
    assert (
        ToolDependencyGuard()
        .evaluate(replace(gated, completed_node_ids=frozenset({"previous", "n"})))
        .action
        == "deny"
    )
    unknown = item.task_plan.nodes[0].model_copy(update={"actor_id": "different"})
    assert (
        ToolDependencyGuard()
        .evaluate(replace(item, task_plan=TrustedTaskPlan(plan_id="unknown", nodes=(unknown,))))
        .action
        == "deny"
    )


def test_plan_rejects_forward_or_unknown_dependencies() -> None:
    node = request().task_plan.nodes[0].model_copy(update={"predecessor_ids": ("future",)})
    with pytest.raises(ValidationError):
        TrustedTaskPlan(plan_id="bad", nodes=(node,))


def test_memory_quarantine_preserves_write_but_blocks_later_control_read() -> None:
    gate = DynamicRuleMemoryIsolator()
    item = request()
    item = replace(
        item,
        memory_key="shared",
        memory_operation="write",
        memory_untrusted=True,
        memory_artifact_ids=("source",),
    )
    assert gate.evaluate(item).action == "allow"
    assert len(gate.quarantine) == 1
    assert gate.evaluate(replace(item, memory_operation="read")).action == "quarantine"
    assert len(gate.quarantine) == 1
    assert (
        gate.evaluate(replace(item, memory_key="clean", memory_untrusted=False)).action == "allow"
    )


def test_revoked_origin_isolated_and_rules_require_trusted_issuer() -> None:
    item = request()
    gate = DynamicRuleMemoryIsolator()
    with pytest.raises(ValueError, match="trusted_rule_issuer"):
        gate.update_rules(PrincipalType.SKILL, item.task_plan, "untrusted-update")
    gate.update_rules(PrincipalType.USER, item.task_plan, "trusted-update")
    revoked = item.signals.model_copy(update={"revoked_origin": True})
    assert (
        gate.evaluate(
            replace(
                item,
                signals=revoked,
                memory_key="old",
                memory_operation="read",
                memory_artifact_ids=("old-memory",),
            )
        ).action
        == "quarantine"
    )
    assert len(gate.rule_updates) == 1
    assert gate.evaluate(replace(item, authorized=False)).action == "deny"


def test_causal_requires_real_paired_assessment() -> None:
    item = request()
    high = item.signals.model_copy(update={"candidate_influence": True, "sink_severity": 4})
    item = replace(item, signals=high)
    gate = CausalAttributionGate()
    unavailable = CausalAssessment(status="not_available", reason="checkpoint_missing")
    assert gate.evaluate(item, unavailable).abstain
    proof = CausalAssessment(
        status="measured",
        reason="paired_receipts",
        pair_id="p",
        y_original=True,
        y_neutral=False,
        ci=1,
        evidence_ids=("original", "neutral"),
    )
    assert gate.evaluate(item, proof).action == "deny"
    survives = proof.model_copy(update={"y_neutral": True, "ci": 0})
    assert gate.evaluate(item, survives).action == "allow"
    assert gate.evaluate(replace(item, authorized=False), survives).action == "confirm"
    with pytest.raises(ValidationError):
        CausalAssessment(status="measured", reason="fake_zero", ci=0)


def test_trusted_rule_update_changes_enforced_plan() -> None:
    gate = DynamicRuleMemoryIsolator()
    item = request()
    gate.update_rules(
        PrincipalType.TRUSTED_POLICY, TrustedTaskPlan(plan_id="revised", nodes=()), "update"
    )
    assert gate.evaluate(item).action == "deny"
    assert gate.evaluate(item).reason == "DYNAMIC_TASK_DEVIATION"


def test_legal_high_sensitivity_operation_does_not_spend_replay_budget() -> None:
    item = request()
    signals = item.signals.model_copy(
        update={"candidate_influence": True, "sink_severity": 4, "target_effect_requested": False}
    )
    assert not CausalAttributionGate.requires_replay(replace(item, signals=signals))
