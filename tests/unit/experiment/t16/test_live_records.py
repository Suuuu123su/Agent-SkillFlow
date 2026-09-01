from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit.experiment.t16.test_live_agent import (
    ScriptedClient,
    _config,
    _design,
    _final_turn,
    _function_turn,
)

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent import execute_live_trial
from skillflow.experiment.t16.live_records import (
    LiveSessionRecord,
    LiveToolCallAudit,
    LiveTrialRecord,
)


def _record() -> LiveTrialRecord:
    config = _config()
    return execute_live_trial(
        _design("c1-p11"),
        config,
        ScriptedClient([_function_turn("operation-1"), _final_turn()]),
        BudgetLedger(config.budget).begin_run(),
    ).record


def _no_harm_record() -> LiveTrialRecord:
    config = _config()
    return execute_live_trial(
        _design("c1-p00"),
        config,
        ScriptedClient([_final_turn()]),
        BudgetLedger(config.budget).begin_run(),
    ).record


PathPart = str | int
Update = tuple[tuple[PathPart, ...], object]


def _apply_updates(payload: dict[str, Any], updates: list[Update]) -> None:
    for path, value in updates:
        target: Any = payload
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value


def _assert_error_type(
    model: type[LiveToolCallAudit] | type[LiveSessionRecord] | type[LiveTrialRecord],
    payload: dict[str, Any],
    expected_type: str,
) -> None:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(payload)
    assert expected_type in {str(item["type"]) for item in caught.value.errors()}


@pytest.mark.parametrize(
    "update",
    [
        {"accepted": True, "rejection_reason": "schema_error"},
        {
            "accepted": False,
            "rejection_reason": "unknown_effect_alias",
            "effect_alias": "context-harm",
            "receipt_id": "receipt-invalid",
        },
        {"accepted": True, "effect_alias": None, "receipt_id": "receipt-invalid"},
    ],
)
def test_tool_audit_rejects_accepted_rejected_receipt_contradictions(
    update: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "session_index": 0,
        "call_id": "call-1",
        "tool_name": "skillflow_safe_effect",
        "accepted": True,
        "effect_alias": "context-harm",
        "receipt_id": "receipt-valid",
    }
    payload.update(update)

    with pytest.raises(ValidationError):
        LiveToolCallAudit.model_validate(payload)


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            {
                "session_index": 0,
                "call_id": "call-rejected-without-reason",
                "tool_name": "read_asset",
                "accepted": False,
            },
            "t16c_tool_acceptance_mismatch",
        ),
        (
            {
                "session_index": 0,
                "call_id": "call-wrong-tool",
                "tool_name": "read_asset",
                "accepted": True,
                "effect_alias": "context-harm",
                "receipt_id": "receipt-valid",
            },
            "t16c_effect_alias_wrong_tool",
        ),
        (
            {
                "session_index": 0,
                "call_id": "call-unknown-without-alias",
                "tool_name": "skillflow_safe_effect",
                "accepted": False,
                "rejection_reason": "unknown_effect_alias",
            },
            "t16c_unknown_effect_alias_missing",
        ),
        (
            {
                "session_index": 0,
                "call_id": "call-schema-with-alias",
                "tool_name": "skillflow_safe_effect",
                "accepted": False,
                "rejection_reason": "schema_error",
                "effect_alias": "context-harm",
            },
            "t16c_non_effect_rejection_has_alias",
        ),
    ],
)
def test_tool_audit_rejects_each_strict_contract_branch(
    payload: dict[str, object],
    expected_type: str,
) -> None:
    _assert_error_type(LiveToolCallAudit, payload, expected_type)


def test_session_rejects_tool_audit_from_another_session() -> None:
    session_payload = _record().sessions[0].model_dump(mode="json")
    session_payload["tool_calls"][0]["session_index"] = 7

    with pytest.raises(ValidationError):
        LiveSessionRecord.model_validate(session_payload)


@pytest.mark.parametrize(
    ("updates", "expected_type"),
    [
        (
            [(("expected_target_effect_aliases",), ["context-harm", "context-harm"])],
            "t16c_session_expected_alias_duplicate",
        ),
        (
            [(("refusal",), True), (("schema_rejection",), True)],
            "t16c_session_outcome_mismatch",
        ),
        (
            [(("timeout",), True)],
            "t16c_session_outcome_mismatch",
        ),
        (
            [(("provider_status_code",), 500)],
            "t16c_provider_diagnostic_without_failure",
        ),
    ],
)
def test_session_rejects_duplicate_alias_terminal_and_diagnostic_drift(
    updates: list[Update],
    expected_type: str,
) -> None:
    payload = _record().sessions[0].model_dump(mode="json")
    _apply_updates(payload, updates)

    _assert_error_type(LiveSessionRecord, payload, expected_type)


def test_new_record_rejects_global_expected_alias_drift() -> None:
    payload = _record().model_dump(mode="json")
    payload["expected_target_effect_aliases"] = ["different-effect"]

    with pytest.raises(ValidationError):
        LiveTrialRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("updates", "expected_type"),
    [
        (
            [(("unauthorized_effect_execution",), True)],
            "t16c_unauthorized_effect_mismatch",
        ),
        (
            [(("intervention_removed_fields",), ["authorization_claim"])],
            "t16c_intervention_audit_mismatch",
        ),
        (
            [(("baseline_reason",), "IMPLICIT_TEXT_AUTHORIZATION")],
            "t16c_alr_reason_without_receipt",
        ),
        (
            [(("sessions",), [])],
            "t16c_live_record_inconsistent",
        ),
        (
            [(("expected_target_effect_aliases",), ["context-harm", "context-harm"])],
            "t16c_live_record_inconsistent",
        ),
        (
            [(("sessions", 0, "expected_target_effect_aliases"), ["different-effect"])],
            "t16c_live_record_inconsistent",
        ),
        (
            [
                (
                    ("expected_target_effect_aliases",),
                    ["context-harm", "different-effect"],
                ),
                (
                    ("sessions", 0, "expected_target_effect_aliases"),
                    ["different-effect"],
                ),
            ],
            "t16c_live_record_inconsistent",
        ),
        (
            [(("result", "receipt_id"), "receipt-different")],
            "t16c_live_record_inconsistent",
        ),
        (
            [(("result", "api_call_count"), 999)],
            "t16c_live_record_inconsistent",
        ),
        (
            [(("result", "latency_ms"), 999)],
            "t16c_live_record_inconsistent",
        ),
        (
            [(("result", "estimated_cost_usd"), "9.99")],
            "t16c_live_record_inconsistent",
        ),
        (
            [(("result", "token_usage", "input_tokens"), 101)],
            "t16c_live_record_inconsistent",
        ),
        (
            [(("result", "refusal"), True)],
            "t16c_live_record_inconsistent",
        ),
    ],
)
def test_v02_trial_rejects_authorization_session_receipt_and_telemetry_drift(
    updates: list[Update],
    expected_type: str,
) -> None:
    payload = _record().model_dump(mode="json")
    _apply_updates(payload, updates)

    _assert_error_type(LiveTrialRecord, payload, expected_type)


def test_v02_trial_rejects_duplicate_or_out_of_order_session_indices() -> None:
    payload = _record().model_dump(mode="json")
    duplicate = payload["sessions"][0].copy()
    payload["sessions"].append(duplicate)

    _assert_error_type(LiveTrialRecord, payload, "t16c_live_record_inconsistent")


def test_v02_trial_rejects_requested_flag_not_derived_from_audit() -> None:
    payload = _no_harm_record().model_dump(mode="json")
    payload["result"]["target_effect_requested"] = True

    _assert_error_type(LiveTrialRecord, payload, "t16c_live_record_inconsistent")


def test_v02_trial_rejects_executed_flag_not_derived_from_receipt() -> None:
    payload = _record().model_dump(mode="json")
    payload["result"].update(
        {
            "target_effect_executed": False,
            "receipt_id": None,
            "outcome": "completed_without_harm",
        }
    )

    _assert_error_type(LiveTrialRecord, payload, "t16c_live_record_inconsistent")


def _record_payload_with_observation() -> dict[str, Any]:
    payload = _record().model_dump(mode="json")
    payload["sessions"][0]["session_index"] = 1
    payload["sessions"][0]["tool_calls"][0]["session_index"] = 1
    payload["session_observations"] = [
        {
            "session_index": 1,
            "target_effect_requested": True,
            "target_effect_executed": True,
            "receipt_id": payload["result"]["receipt_id"],
        }
    ]
    LiveTrialRecord.model_validate(payload)
    return payload


@pytest.mark.parametrize(
    "updates",
    [
        [(("session_observations", 0, "session_index"), 2)],
        [
            (
                ("session_observations",),
                [
                    {
                        "session_index": 1,
                        "target_effect_requested": True,
                        "target_effect_executed": True,
                        "receipt_id": "receipt-placeholder",
                    },
                    {
                        "session_index": 1,
                        "target_effect_requested": True,
                        "target_effect_executed": True,
                        "receipt_id": "receipt-placeholder",
                    },
                ],
            )
        ],
        [
            (("session_observations", 0, "target_effect_requested"), False),
            (("session_observations", 0, "target_effect_executed"), False),
            (("session_observations", 0, "receipt_id"), None),
        ],
        [
            (("session_observations", 0, "target_effect_executed"), False),
            (("session_observations", 0, "receipt_id"), None),
        ],
        [(("session_observations", 0, "receipt_id"), "receipt-different")],
    ],
)
def test_v02_trial_rejects_each_session_observation_drift_branch(
    updates: list[Update],
) -> None:
    payload = _record_payload_with_observation()
    if len(updates) == 1 and updates[0][0] == ("session_observations",):
        receipt_id = payload["result"]["receipt_id"]
        for observation in updates[0][1]:
            observation["receipt_id"] = receipt_id
    _apply_updates(payload, updates)

    _assert_error_type(LiveTrialRecord, payload, "t16c_live_record_inconsistent")


def test_explicit_legacy_record_without_expected_alias_fields_remains_readable() -> None:
    payload = _record().model_dump(mode="json")
    payload["schema_version"] = "0.1"
    payload.pop("phase_contract_sha256")
    payload.pop("expected_target_effect_aliases")
    for session in payload["sessions"]:
        session.pop("expected_target_effect_aliases")

    legacy = LiveTrialRecord.model_validate(payload)

    assert legacy.schema_version == "0.1"
    assert legacy.phase_contract_sha256 is None
    assert legacy.expected_target_effect_aliases == ()
    assert all(session.expected_target_effect_aliases == () for session in legacy.sessions)


def test_live_record_requires_explicit_schema_version() -> None:
    payload = _record().model_dump(mode="json")
    payload.pop("schema_version")

    _assert_error_type(LiveTrialRecord, payload, "missing")


def test_v02_live_record_requires_phase_contract_sha256() -> None:
    payload = _record().model_dump(mode="json")
    payload.pop("phase_contract_sha256")

    _assert_error_type(LiveTrialRecord, payload, "t16c_phase_contract_missing")
