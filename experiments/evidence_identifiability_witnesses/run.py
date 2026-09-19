"""Three explicitly synthetic indistinguishable-world witnesses, without model calls.

This is a finite executable illustration, not a new impossibility theorem or
an estimate of real attack prevalence. Historical inputs are read-only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
P4 = ROOT / "论文材料/P4_测量证据消融/p4-20260917-123623/code"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def make_document(world):
    """Project declared synthetic event facts; never include a truth label."""
    operation = {
        "id": "request-1", "actor": "skill-1", "action": "network.send",
        "source": "synthetic:/message", "sink": "mock://external",
        "position": 3, "effect_id": "effect-1", "belongs_to_current": True,
    }
    records = [{"id": "receipt-1", "op": "request-1", "effect_id": "effect-1"}]
    grant = {"id": "grant-1", "actor": "skill-1", "action": "network.send"}
    return {
        "id": "unit", "layout": "reference",
        "authorization_contract": "action_registry_v1",
        "observation": {"closed": True, "ops": [operation], "objects": []},
        "receipt": {"closed": True, "records": records if world["executed"] else []},
        "grant": {"closed": True, "records": [grant] if world["grant_issued"] else []},
        "lifecycle": {
            "revocations": [{"target": "grant-1", "position": 2}] if world["revoked_before_request"] else [],
            "grant_issue_positions": {"grant-1": 1} if world["grant_issued"] else {},
            "grant_boundary_sessions": {},
        },
        "scope_lifetime": {"action_only_no_extra_constraints": True},
    }


def independent_truth(world):
    """Evaluate the declared action-registry contract without Analyzer calls."""
    active_authorization = world["grant_issued"] and not world["revoked_before_request"]
    return world["executed"] and not active_authorization


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    predictor = load_module("witness_predictor", P4 / "predictor.py")
    views = load_module("witness_views", P4 / "views.py")
    query = {"query_id": "synthetic-uea", "unit": "unit", "op": "request-1",
             "metric": "UEA", "protocol": "actual_receipt_and_authorization"}
    # Freeze the construction and evaluation contract before any predictions.
    plan = {
        "version": "synthetic-identifiability-witnesses-v1",
        "scope": "action-level UEA; synthetic finite constructions, not live runs",
        "pairs": [
            {"family": "receipt", "profile": "V01", "worlds": [
                {"executed": False, "grant_issued": False, "revoked_before_request": False},
                {"executed": True, "grant_issued": False, "revoked_before_request": False}]},
            {"family": "grant", "profile": "V02", "worlds": [
                {"executed": True, "grant_issued": True, "revoked_before_request": False},
                {"executed": True, "grant_issued": False, "revoked_before_request": False}]},
            {"family": "lifecycle", "profile": "V06", "worlds": [
                {"executed": True, "grant_issued": True, "revoked_before_request": False},
                {"executed": True, "grant_issued": True, "revoked_before_request": True}]},
        ],
        "query": query,
        "negative_control": "No execution suffices to refute UEA even when grant is missing.",
        "input_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [P4 / "predictor.py", P4 / "views.py", Path(__file__)]},
        "new_model_calls": 0, "business_executions": 0,
    }
    (out / "PLAN.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    results = []
    for pair in plan["pairs"]:
        documents = [make_document(w) for w in pair["worlds"]]
        visible = [views.project(d, pair["profile"]) for d in documents]
        truth = [independent_truth(w) for w in pair["worlds"]]
        assert canonical(visible[0]) == canonical(visible[1])
        assert truth == [False, True]
        full = [predictor.Analyzer({"unit": d}).run(query) for d in documents]
        partial = [predictor.Analyzer({"unit": d}).run(query) for d in visible]
        assert all(r["status"] == "point" and r["value"] is t for r, t in zip(full, truth))
        assert all(r["value"] is None and r["status"] in {"unknown", "bounded"} for r in partial)
        # Restore the entire evidence channel together with cross-field bindings.
        # No endpoint/label is copied into the predictor input.
        restored = [predictor.Analyzer({"unit": copy.deepcopy(d)}).run(query) for d in documents]
        assert [r["value"] for r in restored] == truth
        results.append({
            "family": pair["family"], "worlds": pair["worlds"], "truth": truth,
            "documents": documents, "visible_document": visible[0],
            "visible_hashes": [digest(v) for v in visible],
            "full_results": full, "partial_results": partial, "restored_results": restored,
            "identical_visible_inputs": True, "opposite_contract_truth": True,
            "any_deterministic_point_answer_wrong_on_at_least_one_world": True,
        })
    negative = make_document({"executed": False, "grant_issued": False, "revoked_before_request": False})
    control = predictor.Analyzer({"unit": views.project(negative, "V02")}).run(query)
    assert control["status"] == "point" and control["value"] is False
    (out / "WITNESSES.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    summary = {
        "status": "COMPLETED_SYNTHETIC_CONSTRUCT_VALIDATION", "pairs": len(results),
        "worlds": 2 * len(results), "same_visible_opposite_truth_pairs": len(results),
        "full_correct_worlds": 2 * len(results), "partial_abstaining_worlds": 2 * len(results),
        "restored_correct_worlds": 2 * len(results), "negative_control": control,
        "plan_sha256": hashlib.sha256((out / "PLAN.json").read_bytes()).hexdigest(),
        "new_model_calls": 0, "business_executions": 0,
        "scope_limit": "Three constructed UEA witness pairs; not ALR/RIR general proof, prevalence, or natural-language accuracy.",
    }
    (out / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (out / "README.md").write_text(
        "# 缺证不可辨识的合成见证\n\n"
        "本实验构造三对动作级 UEA 世界，分别只在实际执行回执、授权、撤销时序上不同。"
        "删除对应证据及其跨字段副本后，每对可见输入逐字节相同，而独立合同真值相反。"
        "因此，任何仅依据该可见输入的确定性点判断都至少在一个世界上错误；这一逻辑是一般性的，"
        "本实验不把它包装成新定理。\n\n"
        "实测：3/3 对满足同观察异真值；完整输入6/6正确，缺证输入6/6保留未知，"
        "恢复证据后6/6正确。负对照表明：无实际执行时，即使缺授权信息也可确定UEA为假。\n\n"
        "所有世界均为明确构造的有限例子，没有真实模型调用或网络发送。"
        "它们说明有限合同的观察边界，不测量自然攻击发生率，也不证明一般ALR/RIR语义。\n\n"
        "复现：`python -B experiments/evidence_identifiability_witnesses/run.py --out /tmp/skillflow-witness-new`"
        "（输出目录必须不存在）。完整输入、许可视图与结果见WITNESSES.json；预先冻结计划见PLAN.json。\n",
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "negative_control"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
