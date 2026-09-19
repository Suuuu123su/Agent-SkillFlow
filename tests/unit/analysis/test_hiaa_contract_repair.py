"""Behavioral regression tests for the versioned historical HIAA correction."""

import copy
import importlib.util
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load_module("hiaa_repair_contract_test", ROOT / "experiments/hiaa_contract_repair/contract.py")
frozen = load_module("hiaa_frozen_test", ROOT / "论文材料/P4_测量证据消融/p4-20260917-123623/code/predictor.py")
views = load_module("hiaa_views_test", ROOT / "论文材料/P4_测量证据消融/p4-20260917-123623/code/views.py")
Analyzer = contract.corrected_analyzer(frozen.Analyzer)


def example():
    documents, members = {}, []
    for repeat in [1, 2]:
        for cell in ["p00", "p01", "p10", "p11"]:
            uid = f"run-{repeat}-{cell}"
            positive = cell == "p11" and repeat == 1
            operations = [{"id": uid + "op", "effect_id": uid + "effect", "action": "network.send"}] if positive else []
            receipts = [{"op": uid + "op", "effect_id": uid + "effect"}] if positive else []
            documents[uid] = {
                "id": uid, "layout": "legacy",
                "failure": {"run_status": "completed", "issues": [], "steps": [{"behavior": "normal", "schema_valid": True}]},
                "observation": {"closed": True, "ops": operations},
                "receipt": {"closed": True, "records": receipts},
                "lifecycle": {"sessions": []},
            }
            members.append({"unit": uid, "cell": cell, "cluster": "s05", "repeat": repeat, "selector": {"action": "network.send"}})
    documents["run-2-p00"]["failure"]["steps"][0]["behavior"] = "no_call"
    documents["grid"] = {"id": "grid", "design": {"members": members, "cells": ["p00", "p01", "p10", "p11"]}}
    query = {"query_id": "query", "unit": "grid", "metric": "HIAA_run", "protocol": "valid_only"}
    return documents, query


def check_excludes_entire_quartet_for_any_original_p3_disqualifier(mutation):
    documents, query = example()
    failure = documents["run-2-p00"]["failure"]
    failure["steps"][0]["behavior"] = "normal"
    if mutation in ["no_call", "refusal"]:
        failure["steps"][0]["behavior"] = mutation
    elif mutation == "not_completed":
        failure["run_status"] = "interrupted"
    else:
        failure["issues"] = ["transport_error"]
    result = Analyzer(documents).run(query)
    assert result["value"] == 1
    assert {v["denominator"] for v in result["details"]["cells"].values()} == {1}
    assert {v["planned"] for v in result["details"]["cells"].values()} == {2}


def check_scheduled_includes_no_call_and_uses_frozen_estimator():
    documents, query = example()
    query["protocol"] = "scheduled"
    assert Analyzer(documents).run(query) == frozen.Analyzer(documents).run(query)
    assert Analyzer(documents).run(query)["value"] == 0.5


def check_failure_withheld_stays_unknown_despite_old_labels_and_closed_observation():
    documents, query = example()
    for document in documents.values():
        document["behavior_valid"] = True
        document["cached_eligibility"] = True
    projected = views.project(documents, "V09")
    assert projected["run-1-p00"]["failure"] is None
    result = Analyzer(projected).run(query)
    assert result["eligibility"] is None
    assert result["status"] == "unknown"
    assert result["reason"] == "valid_only_qualification_unknown"
    assert "run-1-p00#/failure" in result["missing_evidence"]
    assert not any("cached" in path or "behavior_valid" in path for path in result["used_evidence"])


def check_missing_run_status_is_unknown_not_inferred_from_closed_observation():
    documents, query = example()
    del documents["run-1-p00"]["failure"]["run_status"]
    result = Analyzer(documents).run(query)
    assert result["eligibility"] is None
    assert result["status"] == "unknown"


def check_duplicate_cell_cannot_complete_four_cell_group():
    documents, query = example()
    documents["grid"]["design"]["members"][3]["cell"] = "p10"
    result = Analyzer(documents).run(query)
    assert result["eligibility"] is False
    assert result["status"] == "not_applicable"


def check_incomplete_quartet_is_excluded():
    documents, query = example()
    documents["grid"]["design"]["members"].pop(3)
    assert Analyzer(documents).run(query)["status"] == "not_applicable"


def check_non_hiaa_predictions_are_identical():
    documents, _ = example()
    for metric in ["failure_taxonomy", "HIAA_Y"]:
        query = {"query_id": metric, "metric": metric, "unit": "run-1-p11", "protocol": "unchanged", "selector": {"action": "network.send"}}
        assert Analyzer(documents).run(query) == frozen.Analyzer(documents).run(query)


def check_negative_controls_preserve_corrected_values_and_denominators(view):
    documents, query = example()
    full = Analyzer(copy.deepcopy(documents)).run(query)
    ablated = Analyzer(views.project(documents, view)).run(views.project(query, view))
    for key in ["eligibility", "status", "value", "lower", "upper", "details"]:
        assert full[key] == ablated[key]


def check_known_failure_dominates_missing_qualification():
    assert contract.qualification({"run_status": None, "issues": [], "steps": [{"behavior": "no_call"}]}) is False
    assert contract.qualification(None) is None


class HiaaContractRepairTests(unittest.TestCase):
    """Standard-library runner; also collected by the repository's pytest runner."""

    def test_no_call(self):
        check_excludes_entire_quartet_for_any_original_p3_disqualifier("no_call")

    def test_refusal(self):
        check_excludes_entire_quartet_for_any_original_p3_disqualifier("refusal")

    def test_not_completed(self):
        check_excludes_entire_quartet_for_any_original_p3_disqualifier("not_completed")

    def test_issues(self):
        check_excludes_entire_quartet_for_any_original_p3_disqualifier("issues")

    def test_scheduled(self):
        check_scheduled_includes_no_call_and_uses_frozen_estimator()

    def test_failure_withheld(self):
        check_failure_withheld_stays_unknown_despite_old_labels_and_closed_observation()

    def test_missing_status(self):
        check_missing_run_status_is_unknown_not_inferred_from_closed_observation()

    def test_duplicate_cell(self):
        check_duplicate_cell_cannot_complete_four_cell_group()

    def test_incomplete_quartet(self):
        check_incomplete_quartet_is_excluded()

    def test_non_hiaa(self):
        check_non_hiaa_predictions_are_identical()

    def test_metadata_negative_control(self):
        check_negative_controls_preserve_corrected_values_and_denominators("V11")

    def test_rename_negative_control(self):
        check_negative_controls_preserve_corrected_values_and_denominators("V12")

    def test_known_failure_dominates_missing(self):
        check_known_failure_dominates_missing_qualification()


if __name__ == "__main__":
    unittest.main(verbosity=2)
