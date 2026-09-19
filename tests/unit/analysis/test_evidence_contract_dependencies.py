"""Independent fixtures for the versioned nine-channel interface boundary."""

import copy
import itertools

import pytest

from experiments.evidence_contract_validation.dependencies import (
    CHANNELS,
    VERSION,
    apply_bundle,
    build_ledger,
    canonical_bytes,
    explain_missing,
    project,
    receive_bundle,
    restoration_bundle,
)


def fixture_document():
    """A hand-written cross-field fixture, not copied from the rule registry."""
    branch = {
        "id": "identity-branch",
        "receipt": {"records": [{"effect": "branch-effect"}], "closed": True},
        "provenance": {"parents": {"child": ["untrusted-parent"]}},
        "lifecycle": {"sessions": [{"observation_complete": True}]},
        "counterfactual": {"source_object": "nested-source"},
    }
    return {
        "id": "development-contract-fixture",
        "public": {"protocol": "fixture-v1"},
        "receipt": {"records": [{"effect": "real-effect"}], "closed": True},
        "grant": {"records": [{"id": "g-1", "scope": "one-file", "lifetime": "task"}], "closed": True},
        "provenance": {"source": "untrusted-source"},
        "counterfactual": {"pair": {"source_object": "claim-object", "identity": branch,
                                     "qualification": {"schema_valid": True}, "neutral": None}},
        "task_success_evidence": {"artifacts": [{"digest": "123", "session_id": "session-a"}]},
        "lifecycle": {"sessions": [{"observation_complete": True, "id": "session-a"}],
                      "grant_issue_positions": {"g-1": 1},
                      "grant_boundary_sessions": {"g-1": "session-a"}},
        "scope_lifetime": {"grant_limits": {"g-1": {"scope": "one-file", "lifetime": "task",
                                                     "session_id": "session-a"}},
                           "permission_limits": {"p-1": {"scope": "one-file"}}},
        "decision_reason": {"op-1": "registered mechanical reason"},
        "failure": {"collector_complete": True, "steps": [{"schema_valid": True}]},
    }



def sandbox_schema_fixture():
    """Independent fixture of the new controlled-runner adapter output schema."""
    return {
        "id": "dev-sandbox-schema", "contract_version": "controlled-persistent-effect-v1",
        "public": {"protocol": "controlled-persistent-effect-v1", "source_class": "controlled_program"},
        "receipt": {"operation": {"action": "file_write", "resource": "output.txt"},
                    "ack": {"status": "committed", "artifact_hashes": {"output.txt": "good-hash"}}},
        "grant": {"closed": True, "records": [{"grant_id": "g-a", "action": "file_write"}]},
        "scope_lifetime": {"limits": {"g-a": {"resource": "output.txt"}}},
        "lifecycle": {"action_time": 10, "current_session": "s-a",
                      "grant_times": {"g-a": {"issued": 1, "expires": 20, "grant_session": "s-a"}},
                      "revocations": [{"grant_id": "g-a", "revoked_ns": 30}],
                      "artifact_binding": {"session_id": "s-a", "task_id": "t-a"},
                      "required_binding": {"session_id": "s-a", "task_id": "t-a"}},
        "task_success_evidence": {"artifacts": [{"path": "output.txt", "required_hash": "good-hash",
                                                "observed_hash": "good-hash"}],
                                  "tables": [], "requires_committed_effect": True},
        "failure": {"monitor_closed": True, "operation": {"action": "file_write", "resource": "output.txt"},
                    "changed_path_events": 1,
                    "changes": [{"path": "output.txt", "before_sha256": "old-hash", "after_sha256": "good-hash"}],
                    "return_code": 0, "timed_out": False},
        "provenance": {"reference_scope": "data_lineage_only", "reason_contrast_available": False},
        "decision_reason": {"recorded_agent_reason": None},
        "counterfactual": {"identity": None, "neutral": None, "confirmed_prefix": None},
    }

def at(document, path):
    value = document
    for part in path.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def set_at(document, path, value):
    parts = path.lstrip("/").split("/")
    parent = document
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    if isinstance(parent, list):
        parent[int(parts[-1])] = value
    else:
        parent[parts[-1]] = value


@pytest.mark.parametrize("document_factory", [fixture_document, sandbox_schema_fixture])
@pytest.mark.parametrize("mask", range(512))
def test_all_512_masks_projection_order_idempotence_and_hidden_values(mask, document_factory):
    document = document_factory()
    visible = {channel for index, channel in enumerate(CHANNELS) if mask & (1 << index)}
    expected = project(document, visible)
    assert project(expected, visible) == expected
    hidden = [channel for channel in CHANNELS if channel not in visible]
    for order in (hidden, hidden[::-1]):
        sequential = document
        for channel in order:
            sequential = project(sequential, set(CHANNELS) - {channel})
        assert sequential == expected
    # Mutate one hidden frontier at a time. Its shape, contents and byte length
    # are arbitrary; projection must return exactly the same permitted bytes.
    ledger = build_ledger(document)
    frontier = []
    for entry in ledger["entries"]:
        if set(entry["requires"]) <= visible:
            continue
        if not any(entry["path"].startswith(path + "/") for path in frontier):
            frontier.append(entry["path"])
    for path in frontier:
        changed = copy.deepcopy(document)
        set_at(changed, path, {"unseen": ["arbitrary-hidden-value" * 7, False, None]})
        assert canonical_bytes(project(changed, visible)) == canonical_bytes(expected)
    assert document == document_factory()


def test_registered_paths_cover_independently_specified_cross_field_dependencies():
    entries = {e["path"]: e for e in build_ledger(fixture_document())["entries"]}
    expected = {
        "/counterfactual/pair/source_object": ("provenance", {"counterfactual", "provenance"}),
        "/counterfactual/pair/identity/counterfactual/source_object":
            ("provenance", {"counterfactual", "provenance"}),
        "/counterfactual/pair/qualification": ("failure", {"counterfactual", "failure"}),
        "/lifecycle/sessions/0/observation_complete": ("failure", {"lifecycle", "failure"}),
        "/lifecycle/grant_issue_positions": ("lifecycle", {"lifecycle", "grant"}),
        "/lifecycle/grant_boundary_sessions": ("lifecycle", {"lifecycle", "grant"}),
        "/scope_lifetime/grant_limits": ("scope_lifetime", {"scope_lifetime", "grant"}),
        "/scope_lifetime/grant_limits/g-1/session_id":
            ("lifecycle", {"scope_lifetime", "grant", "lifecycle"}),
        "/task_success_evidence/artifacts/0/session_id":
            ("lifecycle", {"task_success_evidence", "lifecycle"}),
        "/grant/records/0/scope": ("scope_lifetime", {"grant", "scope_lifetime"}),
        "/grant/records/0/lifetime": ("scope_lifetime", {"grant", "scope_lifetime"}),
    }
    for path, (owner, requires) in expected.items():
        assert entries[path]["owner"] == owner
        assert set(entries[path]["requires"]) == requires
        assert entries[path]["token"] == VERSION + "#" + path
    assert len({entry["token"] for entry in entries.values()}) == len(entries)


def test_every_changed_path_has_a_unique_registered_owner():
    document = fixture_document()
    entries = {e["path"]: e for e in build_ledger(document)["entries"]}

    def changed_paths(before, after, path=""):
        if before == after:
            return []
        if isinstance(before, dict) and isinstance(after, dict):
            return list(itertools.chain.from_iterable(
                changed_paths(value, after[key], path + "/" + key)
                for key, value in before.items()))
        if isinstance(before, list) and isinstance(after, list):
            return list(itertools.chain.from_iterable(
                changed_paths(value, after[index], path + "/" + str(index))
                for index, value in enumerate(before)))
        return [path]

    for channel in CHANNELS:
        for path in changed_paths(document, project(document, set(CHANNELS) - {channel})):
            assert entries[path]["owner"] in CHANNELS
            assert channel in entries[path]["requires"]


@pytest.mark.parametrize("document_factory", [fixture_document, sandbox_schema_fixture])
def test_restore_every_channel_under_every_mask_uses_only_acquired_closure(document_factory):
    document = document_factory()
    for mask in range(512):
        visible = {channel for index, channel in enumerate(CHANNELS) if mask & (1 << index)}
        initial = project(document, visible)
        for channel in CHANNELS:
            bundle = restoration_bundle(document, visible, channel)
            assert apply_bundle(initial, bundle) == project(document, visible | {channel})
            assert all(set(atom["requires"]) <= visible | {channel} for atom in bundle["atoms"])
            assert all(not set(atom["requires"]) <= visible for atom in bundle["atoms"])


def test_nested_provenance_restore_is_not_free_and_preserves_other_hidden_channels():
    document = fixture_document()
    acquired = {"counterfactual", "receipt"}
    initial = project(document, acquired)
    assert initial["counterfactual"]["pair"]["source_object"] is None
    bundle = restoration_bundle(document, acquired, "provenance")
    patched_paths = {patch["path"] for patch in bundle["patches"]}
    assert "/counterfactual/pair/source_object" in patched_paths
    assert "/counterfactual/pair/identity/counterfactual/source_object" in patched_paths
    result = apply_bundle(initial, bundle)
    assert result["counterfactual"]["pair"]["source_object"] == "claim-object"
    assert result["counterfactual"]["pair"]["qualification"] is None
    initial_bytes = len(canonical_bytes(initial))
    actual_response_bytes = len(canonical_bytes(bundle))
    result, total = receive_bundle(initial, bundle, initial_bytes, initial_bytes + actual_response_bytes)
    assert total == initial_bytes + actual_response_bytes
    assert total > len(canonical_bytes(result))
    with pytest.raises(ValueError, match="BUNDLE_EXCEEDS_REMAINING_BUDGET"):
        receive_bundle(initial, bundle, initial_bytes, total - 1)
    assert initial["counterfactual"]["pair"]["source_object"] is None


def test_every_restoration_order_reaches_same_full_document():
    document = fixture_document()
    for order in (CHANNELS, CHANNELS[::-1], CHANNELS[4:] + CHANNELS[:4]):
        acquired = set()
        visible = project(document, acquired)
        total = len(canonical_bytes(visible))
        for channel in order:
            bundle = restoration_bundle(document, acquired, channel)
            visible, total = receive_bundle(visible, bundle, total, 10**9)
            acquired.add(channel)
        assert visible == document
        assert total > len(canonical_bytes(document))


def test_no_prerequisite_auto_acquisition_and_no_stale_mirror_restore():
    document = fixture_document()
    bundle = restoration_bundle(document, set(), "provenance")
    assert bundle["acquired_channels"] == ["provenance"]
    restored = apply_bundle(project(document, set()), bundle)
    assert restored["counterfactual"] is None
    bundle = restoration_bundle(document, {"provenance"}, "counterfactual")
    restored = apply_bundle(restored, bundle)
    assert restored["counterfactual"]["pair"]["source_object"] == "claim-object"
    assert restored["counterfactual"]["pair"]["identity"]["receipt"] is None


def test_evaluation_labels_and_full_documents_never_enter_visible_interface():
    document = fixture_document()
    poisoned = copy.deepcopy(document)
    poisoned.update(oracle={"answer": True}, Full={"status": "point"},
                    labels=["unsafe"], hidden_documents={"private": document})
    poisoned["receipt"]["oracle"] = {"leak": "nested"}
    for visible in (set(), {"receipt"}, set(CHANNELS)):
        assert project(poisoned, visible) == project(document, visible)


def test_unknown_root_and_channel_fail_closed_without_exposing_values():
    document = fixture_document()
    document["unregistered_sensitive_field"] = "must-not-leak"
    with pytest.raises(ValueError, match="Unregistered public root keys") as error:
        project(document, set(CHANNELS))
    assert "must-not-leak" not in str(error.value)
    with pytest.raises(ValueError, match="Unknown evidence channels"):
        project(fixture_document(), {"not-a-channel"})


def test_forged_nested_dependency_and_owner_are_rejected():
    document = fixture_document()
    initial = project(document, set())
    bundle = restoration_bundle(document, set(), "counterfactual")
    forged = copy.deepcopy(bundle)
    forged["patches"][0]["value"]["pair"]["source_object"] = "unauthorized-provenance"
    with pytest.raises(ValueError, match="outside acquired dependency closure"):
        apply_bundle(initial, forged)
    forged = copy.deepcopy(bundle)
    forged["patches"][0]["owner"] = "receipt"
    with pytest.raises(ValueError, match="Unregistered or unauthorized"):
        apply_bundle(initial, forged)


def test_missing_explanation_does_not_overclaim_top_level_analyzer_log():
    result = explain_missing("CI", "precise_control_semantics", {"counterfactual"}, [])
    assert result["complete"] is False
    assert "provenance" in result["missing_channels"]
    assert "failure" in result["missing_channels"]


def test_canonical_utf8_and_retransmission_acknowledgements_are_fully_charged():
    assert canonical_bytes({"z": "证据", "a": 1}) == '{"a":1,"z":"证据"}'.encode()
    document = fixture_document()
    visible = project(document, CHANNELS)
    bundle = restoration_bundle(document, CHANNELS, "provenance")
    assert bundle["patches"] == []
    assert bundle["atoms"] == []
    initial = len(canonical_bytes(visible))
    assert receive_bundle(visible, bundle, initial, 10**9)[1] == initial + len(canonical_bytes(bundle))


def test_legacy_capability_grant_state_is_conservatively_hidden():
    document = {"id": "legacy", "declared_capability_rules": {
        "initial": ["grant-atom", "ordinary-atom"], "unknown_initial_atoms": []}}
    visible = project(document, set(CHANNELS) - {"grant"})
    assert visible["declared_capability_rules"]["initial"] is None
    assert visible["declared_capability_rules"]["unknown_initial_atoms"] is None
    assert apply_bundle(visible, restoration_bundle(document, set(CHANNELS) - {"grant"}, "grant")) == document


def test_new_adapter_paths_have_grant_and_artifact_mirror_owners():
    document = sandbox_schema_fixture()
    entries = {entry["path"]: entry for entry in build_ledger(document)["entries"]}
    expected = {
        "/scope_lifetime/limits": ("scope_lifetime", {"scope_lifetime", "grant"}),
        "/lifecycle/grant_times": ("lifecycle", {"lifecycle", "grant"}),
        "/lifecycle/revocations": ("lifecycle", {"lifecycle", "grant"}),
        "/receipt/ack/artifact_hashes": ("task_success_evidence", {"receipt", "task_success_evidence"}),
        "/failure/changes/0/before_sha256": ("task_success_evidence", {"failure", "task_success_evidence"}),
        "/failure/changes/0/after_sha256": ("task_success_evidence", {"failure", "task_success_evidence"}),
    }
    for path, (owner, requires) in expected.items():
        assert entries[path]["owner"] == owner
        assert set(entries[path]["requires"]) == requires
    visible = project(document, set(CHANNELS) - {"grant", "task_success_evidence"})
    assert visible["scope_lifetime"]["limits"] is None
    assert visible["lifecycle"]["grant_times"] is None
    assert visible["lifecycle"]["revocations"] is None
    assert visible["receipt"]["ack"]["artifact_hashes"] is None
    assert visible["failure"]["changes"][0]["before_sha256"] is None
    assert visible["failure"]["changes"][0]["after_sha256"] is None
    assert visible["failure"]["changed_path_events"] == 1
