"""Reject stale receipts in licensed evidence; no task execution is performed."""
from copy import deepcopy

import pytest

from experiments.evidence_contract_validation.predictor import predict


def _document():
    operation = {"action": "write", "resource": "target", "task_id": "task-1",
                 "session_id": "session-1", "effect_id": "effect-1", "attempt_id": "attempt-1",
                 "started_ns": 100, "finished_ns": 200}
    ack = {key: value for key, value in operation.items() if key not in ("started_ns", "finished_ns")}
    ack.update(status="committed", time_ns=150, receipt_id="receipt-1")
    return {"receipt": {"operation": operation, "ack": ack},
            "grant": {"closed": True, "records": []}}


def test_current_bound_receipt_can_establish_unauthorized_effect():
    result = predict("UEA", _document())
    assert result["status"] == "point" and result["value"] is True


@pytest.mark.parametrize("field", ["action", "resource", "task_id", "session_id", "effect_id", "attempt_id"])
def test_receipt_for_another_action_attempt_or_session_is_unknown(field):
    document = _document()
    document["receipt"]["ack"][field] = "stale"
    result = predict("UEA", document)
    assert result["status"] == "unknown"


@pytest.mark.parametrize("ack_time", [99, 201])
def test_receipt_outside_supervised_interval_is_unknown(ack_time):
    document = _document()
    document["receipt"]["ack"]["time_ns"] = ack_time
    assert predict("UEA", document)["status"] == "unknown"


@pytest.mark.parametrize("ack_time", [100, 200])
def test_action_interval_boundaries_are_inclusive(ack_time):
    document = _document()
    document["receipt"]["ack"]["time_ns"] = ack_time
    assert predict("UEA", document)["value"] is True


@pytest.mark.parametrize("field", ["action", "resource", "task_id", "session_id", "effect_id", "attempt_id"])
def test_two_missing_bindings_cannot_validate_each_other(field):
    document = _document()
    document["receipt"]["operation"][field] = None
    document["receipt"]["ack"][field] = None
    assert predict("UEA", document)["status"] == "unknown"


def test_complete_no_change_monitor_overrides_stale_or_conflicting_ack():
    document = _document()
    document["receipt"]["ack"]["effect_id"] = "stale-effect"
    document["failure"] = {"monitor_closed": True, "operation": deepcopy(document["receipt"]["operation"]),
                            "changes": []}
    result = predict("UEA", document)
    assert result["status"] == "point" and result["value"] is False
    document["receipt"]["ack"]["effect_id"] = "effect-1"
    assert predict("UEA", document)["value"] is False


def test_independent_complete_monitor_can_recover_effect_after_invalid_ack():
    document = _document()
    document["receipt"]["ack"]["task_id"] = "different-task"
    document["failure"] = {"monitor_closed": True, "operation": deepcopy(document["receipt"]["operation"]),
                            "changes": [{"path": "result.txt", "effect_id": "effect-1"}]}
    result = predict("UEA", document)
    assert result["status"] == "point" and result["value"] is True


def test_incomplete_monitor_and_invalid_ack_do_not_prove_absence():
    document = _document()
    document["receipt"]["ack"]["status"] = "attempted"
    document["failure"] = {"monitor_closed": False, "operation": deepcopy(document["receipt"]["operation"]),
                            "changes": []}
    assert predict("UEA", document)["status"] == "unknown"