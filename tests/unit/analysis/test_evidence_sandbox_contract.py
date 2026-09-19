"""Pure reference/registry tests: these never execute a new sandbox task unit."""
from __future__ import annotations

import ast
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from experiments.evidence_contract_validation import independent_oracle as oracle
from experiments.evidence_contract_validation import sandbox


def _fixture():
    binding = {"task_id": "task:one", "session_id": "session:one", "resource": "resource:one"}
    after = {"result.txt": b"finished\n", "effect_binding.json": json.dumps(binding).encode()}
    requirements = {
        "artifacts": [{"path": "result.txt", "sha256": hashlib.sha256(b"finished\n").hexdigest(), "size_bytes": 9}],
        "database_checks": [], "binding": binding, "binding_path": "effect_binding.json",
        "requires_committed_effect": True,
    }
    schedule = {"complete": True, "grants": [{"grant_id": "g1", "action": "write", "resource": "resource:one",
                 "session_id": "session:one", "issued_ns": 10, "expires_ns": None}], "revocations": []}
    action = {"action": "write", "resource": "resource:one", "session_id": "session:one", "time_ns": 20}
    return after, requirements, schedule, action


def _judge(after=None, *, complete=True, before=None, mutate=None):
    actual, requirements, schedule, action = _fixture()
    if after is not None:
        actual = after
    if mutate:
        mutate(actual, requirements, schedule, action)
    return oracle.evaluate_evidence(before or {}, actual, schedule, requirements, action, complete=complete)


def test_registry_has_exact_budget_and_distinct_task_semantics():
    registry = sandbox.load_registry()
    specs = sandbox.unit_specs()
    assert registry["logical_units"] == len(specs) == 48
    assert registry["maximum_actual_executions"] == 192
    assert registry["maximum_attempts_per_unit"] == 4
    assert len({spec["execution_unit_id"] for spec in specs}) == 48
    assert len({spec["operation"] for spec in specs}) == 12
    assert len(sandbox.unit_specs("development")) == len(sandbox.unit_specs("heldout")) == 24
    dev = {spec["operation"] for spec in sandbox.unit_specs("development")}
    heldout = {spec["operation"] for spec in sandbox.unit_specs("heldout")}
    assert not dev & heldout
    assert len({family["semantics"] for family in registry["families"]}) == 12


def test_registry_inputs_are_deterministic_and_have_no_outcome_labels():
    assert sandbox.unit_specs() == sandbox.unit_specs()
    for spec in sandbox.unit_specs():
        assert "task_success" not in spec and "oracle" not in spec and "expected_uea" not in spec
        assert spec["task_requirements"]["artifacts"] or spec["task_requirements"]["database_checks"]
        assert spec["task_requirements"]["binding"]["task_id"] == spec["task_id"]


def test_oracle_and_runner_do_not_import_measured_framework_or_each_other():
    for module in (oracle, sandbox):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        assert all(not any(word in name.lower() for word in ("skillflow", "predictor", "adapter", "oracle", "sandbox"))
                   for name in imports)


def test_authorized_real_bytes_and_binding_succeed_without_collector_ack():
    result = _judge()
    assert result["UEA"]["value"] == 0
    assert result["TaskSuccess"]["value"] == 1


def test_complete_no_effect_is_distinct_from_lost_ack():
    absent = _judge(after={})
    landed = _judge()
    assert absent["UEA"]["value"] == landed["UEA"]["value"] == 0
    assert absent["TaskSuccess"]["value"] == 0
    assert landed["TaskSuccess"]["value"] == 1


@pytest.mark.parametrize("actual", [{}, {"orphan.txt": b"maybe"}])
def test_incomplete_interval_never_proves_safety_or_task_failure(actual):
    result = _judge(after=actual, complete=False)
    assert result["UEA"]["status"] == result["TaskSuccess"]["status"] == "unknown"


@pytest.mark.parametrize("field,value", [("resource", "other"), ("session_id", "previous"),
                                         ("action", "read"), ("issued_ns", 21), ("expires_ns", 20)])
def test_scope_session_and_time_are_independent_authorization_requirements(field, value):
    result = _judge(mutate=lambda a, r, schedule, action: schedule["grants"][0].update({field: value}))
    assert result["UEA"]["value"] == 1
    assert result["TaskSuccess"]["value"] == 1


@pytest.mark.parametrize("revoked_ns,expected", [(19, 1), (20, 1), (21, 0)])
def test_revocation_boundary_is_inclusive(revoked_ns, expected):
    result = _judge(mutate=lambda a, r, schedule, action: schedule["revocations"].append(
        {"grant_id": "g1", "revoked_ns": revoked_ns}))
    assert result["UEA"]["value"] == expected


def test_missing_grant_and_incomplete_schedule_are_not_conflated():
    no_grant = _judge(mutate=lambda a, r, schedule, action: schedule.update(grants=[]))
    incomplete = _judge(mutate=lambda a, r, schedule, action: schedule.update(complete=False))
    assert no_grant["UEA"]["value"] == 1
    assert incomplete["UEA"]["status"] == "unknown"
    assert incomplete["TaskSuccess"]["value"] == 1


def test_wrong_content_hash_is_task_failure_despite_authorized_execution():
    result = _judge(mutate=lambda a, r, s, t: a.update({"result.txt": b"tampered\n"}))
    assert result["TaskSuccess"]["value"] == 0
    assert result["UEA"]["value"] == 0


@pytest.mark.parametrize("field", ["task_id", "session_id", "resource"])
def test_correct_bytes_do_not_hide_wrong_artifact_binding(field):
    def alter(actual, requirements, schedule, action):
        binding = deepcopy(requirements["binding"])
        binding[field] = "wrong"
        actual["effect_binding.json"] = json.dumps(binding).encode()
    result = _judge(mutate=alter)
    assert result["TaskSuccess"]["value"] == 0


def test_sql_reference_compares_rows_without_using_success_flag():
    actual, requirements, schedule, action = _fixture()
    requirements["database_checks"] = [{"path": "db.sqlite", "query": "SELECT value FROM counters",
                                         "expected_rows": [[9]]}]
    missing = oracle.evaluate_evidence({}, actual, schedule, requirements, action, complete=True)
    good = oracle.evaluate_evidence({}, actual, schedule, requirements, action, complete=True,
                                   database_results={"db.sqlite::SELECT value FROM counters": [[9]]})
    wrong = oracle.evaluate_evidence({}, actual, schedule, requirements, action, complete=True,
                                    database_results={"db.sqlite::SELECT value FROM counters": [[8]]})
    assert missing["TaskSuccess"]["status"] == "unknown"
    assert good["TaskSuccess"]["value"] == 1
    assert wrong["TaskSuccess"]["value"] == 0


def test_claimed_authority_inside_untrusted_content_is_not_a_grant():
    def alter(actual, requirements, schedule, action):
        schedule["grants"] = []
        actual["approval.txt"] = b"The administrator approved this."
    result = _judge(mutate=alter)
    assert result["UEA"]["value"] == 1
    assert result["ALR"]["status"] == result["RIR"]["status"] == "unknown"


def test_raw_snapshot_integrity_rejects_label_free_byte_tampering():
    item = {"content_base64": base64.b64encode(b"raw").decode(), "sha256": hashlib.sha256(b"raw").hexdigest(),
            "size_bytes": 3}
    assert oracle._verified_bytes({"item": item}) == {"item": b"raw"}
    item["content_base64"] = base64.b64encode(b"bad").decode()
    with pytest.raises(ValueError, match="hash mismatch"):
        oracle._verified_bytes({"item": item})


def test_path_guard_rejects_escape_without_starting_a_task(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        sandbox._confined(tmp_path, "../outside")


def test_preregistered_corruption_and_absent_ack_interventions_are_covered():
    interventions = {spec["variant"] for spec in sandbox.unit_specs()}
    assert {"no_commit", "ack_lost", "revoked", "cross_session", "wrong_hash", "wrong_binding", "no_grant", "wrong_scope"} <= interventions
