import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.analysis.authorization_laundering import (
    AuthorizationAttemptFact,
    AuthorizationClaimNeutralization,
    BaselineReason,
)
from skillflow.analysis.experiment_reporting import (
    ExperimentAggregationFacts,
    build_experiment_report,
)
from skillflow.analysis.hiaa import MatrixRunOutcome, ReachableUnauthorizedEffect
from skillflow.analysis.report_io import write_experiment_risk_report
from skillflow.instrumentation.tool_receipt import (
    ToolReceipt,
    ToolReceiptDraft,
    ToolReceiptIssuer,
)
from skillflow.instrumentation.tool_types import MockToolName
from skillflow.models.advanced_metrics import (
    AttributionKind,
    ResidualActionEvidence,
    ResidualRunObservation,
    SkillRevocationRecord,
)
from skillflow.models.effects import CapabilityEffect, EffectRecord
from skillflow.models.enums import CapabilityAction, Decision, Lifetime, Scope, TrustLevel
from skillflow.models.matrix import HiaaCell
from skillflow.models.metrics import CanonicalEffectKey
from skillflow.models.reports import RISK_REPORT_ADAPTER
from skillflow.models.resources import ResourceRef
from skillflow.models.scenario_parts import EffectSelector

REVOKED_AT = datetime(2026, 1, 1, tzinfo=UTC)
HARM_SELECTOR = EffectSelector(
    alias="network-harm",
    action=CapabilityAction.NETWORK_SEND,
    source_pattern=ResourceRef("memory:/shared"),
    sink_pattern=ResourceRef("mock://external"),
)


def _effect(sink: str) -> CanonicalEffectKey:
    return CanonicalEffectKey(
        source=ResourceRef("memory:/shared"),
        action=CapabilityAction.NETWORK_SEND,
        sink=ResourceRef(sink),
        scope=Scope.EXACT_SINK,
        lifetime=Lifetime.CALL,
    )


def _executed_effect() -> tuple[EffectRecord, ToolReceipt]:
    effect = EffectRecord(
        effect_id="matrix-effect-p11",
        effect_alias=HARM_SELECTOR.alias,
        effect=CapabilityEffect(
            source=ResourceRef("memory:/shared"),
            action=CapabilityAction.NETWORK_SEND,
            sink=ResourceRef("mock://external"),
            scope=Scope.EXACT_SINK,
            lifetime=Lifetime.CALL,
            sensitivity=4,
        ),
        request_event_id="matrix-request-p11",
        decision_id="matrix-decision-p11",
        result_event_id="matrix-result-p11",
        tool_receipt_id="matrix-receipt-p11",
        executed=True,
    )
    receipt = ToolReceiptIssuer().issue(
        ToolReceiptDraft(
            receipt_id="matrix-receipt-p11",
            tool=MockToolName.HTTP_SEND,
            effect_id=effect.effect_id,
            request_event_id=effect.request_event_id,
            result_event_id="matrix-result-p11",
            decision_id=effect.decision_id,
            actor_id="tool-adapter",
            call_id="matrix-call-p11",
            action_id="matrix-action-p11",
            argument_artifact_id="matrix-argument-p11",
            receipt_artifact_id="matrix-receipt-artifact-p11",
            timestamp=REVOKED_AT,
        )
    )
    return effect, receipt


def _facts() -> ExperimentAggregationFacts:
    executed_effect, executed_receipt = _executed_effect()
    matrix = tuple(
        MatrixRunOutcome(
            cell=cell,
            run_id=f"matrix-{cell.value}",
            effects=(executed_effect,) if cell is HiaaCell.P11 else (),
            receipts=(executed_receipt,) if cell is HiaaCell.P11 else (),
        )
        for cell in HiaaCell
    )
    attempts = (
        AuthorizationAttemptFact(
            authorization_request_id="authorization-request-laundered",
            has_matching_grant=False,
            authorization_claim_artifact_id="claim-1",
            authorization_claim_trust=TrustLevel.UNTRUSTED,
            decision_basis_artifact_ids=("claim-1",),
            baseline_reason=BaselineReason.IMPLICIT_TEXT_AUTHORIZATION,
            original_receipt_ids=("receipt-original-1",),
            neutralization=AuthorizationClaimNeutralization(
                replay_id="replay-1",
                neutralized_claim_artifact_id="claim-1",
                original_non_claim_inputs_hash="inputs-1",
                neutral_non_claim_inputs_hash="inputs-1",
            ),
            neutral_baseline_result=Decision.CONFIRM,
            neutral_receipt_ids=(),
            evidence_ids=("claim-1", "replay-1"),
        ),
        AuthorizationAttemptFact(
            authorization_request_id="authorization-request-bypass",
            has_matching_grant=False,
            authorization_claim_artifact_id="claim-2",
            authorization_claim_trust=TrustLevel.UNTRUSTED,
            decision_basis_artifact_ids=("claim-2",),
            baseline_reason=BaselineReason.IMPLICIT_TEXT_AUTHORIZATION,
            original_receipt_ids=("receipt-original-2",),
            neutralization=AuthorizationClaimNeutralization(
                replay_id="replay-2",
                neutralized_claim_artifact_id="claim-2",
                original_non_claim_inputs_hash="inputs-2",
                neutral_non_claim_inputs_hash="inputs-2",
            ),
            neutral_baseline_result=Decision.ALLOW,
            neutral_receipt_ids=("receipt-neutral-2",),
            evidence_ids=("claim-2", "replay-2"),
        ),
    )
    revocation = SkillRevocationRecord(
        skill_id="skill-a",
        revoke_event_id="revoke-event",
        session_index=2,
        revoked_at=REVOKED_AT,
    )
    residual_runs = (
        ResidualRunObservation(
            run_id="residual-1",
            session_index=3,
            started_at=REVOKED_AT + timedelta(hours=1),
            valid=True,
            actions=(
                ResidualActionEvidence(
                    effect_id="effect-rir-1",
                    receipt_id="receipt-rir-1",
                    unauthorized=True,
                    attribution=AttributionKind.GT_INFLUENCE,
                    attributed_skill_id="skill-a",
                    attribution_evidence_ids=("gt-influence-1",),
                    oracle_provenance_evidence_ids=("oracle-path-1",),
                ),
            ),
        ),
        ResidualRunObservation(
            run_id="residual-3",
            session_index=5,
            started_at=REVOKED_AT + timedelta(hours=3),
            valid=True,
            actions=(),
        ),
    )
    return ExperimentAggregationFacts(
        experiment_id="experiment-t11",
        run_ids=tuple(outcome.run_id for outcome in matrix)
        + tuple(run.run_id for run in residual_runs),
        replay_ids=("replay-1", "replay-2"),
        unauthorized_executed_count=3,
        harm_selector=HARM_SELECTOR,
        matrix_outcomes=matrix,
        harness_off_effects=(
            ReachableUnauthorizedEffect(_effect("mock://common"), 1.0, "path-common"),
        ),
        harness_on_effects=(
            ReachableUnauthorizedEffect(_effect("mock://common"), 1.0, "path-common"),
            ReachableUnauthorizedEffect(_effect("mock://external"), 1.0, "path-new"),
        ),
        authorization_attempts=attempts,
        revocation=revocation,
        residual_runs=residual_runs,
    )


def test_t11_experiment_report_exposes_raw_cells_and_all_advanced_metrics(
    tmp_path: Path,
) -> None:
    # Given: 四格、授权配对和撤销后运行的中立聚合事实
    report = build_experiment_report(_facts())
    path = tmp_path / "aggregate-metrics.json"

    # When: 经过判别联合 Schema 复验后写入 Experiment 报告
    write_experiment_risk_report(path, report)
    payload = json.loads(path.read_text(encoding="utf-8"))

    # Then: 原始 outcome/计数/发生率和三类高级指标同时可复核
    assert payload["report_scope"] == "experiment"
    assert payload["harm_selector"]["alias"] == "network-harm"
    assert payload["p11"]["outcomes"] == [True]
    assert payload["p11"]["executed_count"] == 1
    assert payload["p11"]["receipt_ids"] == ["matrix-receipt-p11"]
    assert payload["p11"]["rate"]["value"] == 1.0
    assert payload["HIAA_pot"]["value"] == 1.0
    assert payload["HIAA_run"]["value"] == 1.0
    assert payload["ALR"]["value"] == 0.5
    assert payload["authorization_laundering_request_ids"] == ["authorization-request-laundered"]
    assert payload["plain_authorization_bypass_request_ids"] == ["authorization-request-bypass"]
    assert payload["revocation"]["revoked_at"] == "2026-01-01T00:00:00Z"
    assert payload["RIR_1"]["value"] == 1.0
    assert payload["RIR_3"]["value"] == 0.0


def test_experiment_report_rejects_a_hiaa_value_not_derived_from_raw_cells() -> None:
    payload = build_experiment_report(_facts()).model_dump(mode="json", by_alias=True)
    hiaa = payload["HIAA_run"]
    assert isinstance(hiaa, dict)
    hiaa["value"] = -0.25

    with pytest.raises(ValidationError, match="HIAA_run"):
        RISK_REPORT_ADAPTER.validate_python(payload)


def test_experiment_report_rejects_duplicate_authorization_request_ids() -> None:
    payload = build_experiment_report(_facts()).model_dump(mode="json", by_alias=True)
    attempts = payload["authorization_attempts"]
    assert isinstance(attempts, list)
    first = attempts[0]
    assert isinstance(first, dict)
    attempts.append(dict(first))

    with pytest.raises(ValidationError, match="authorization_request_id"):
        RISK_REPORT_ADAPTER.validate_python(payload)
