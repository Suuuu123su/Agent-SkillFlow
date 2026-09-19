"""Read-only baseline/source audit. No model, network, or business execution.

Run with Python -B from the repository root. Outputs only into --out.
This audit does not import the new experiment predictor or sandbox runner.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "论文材料/修复与补强_20260919"
P4 = ROOT / "论文材料/P4_测量证据消融/p4-20260917-123623"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(raw):
    return [json.loads(x) for x in raw.decode("utf-8-sig").splitlines() if x]


def module(name, code):
    result = types.ModuleType(name)
    exec(compile(code, name, "exec"), result.__dict__)
    return result


def file_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path, values):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows({k: canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in values)


def ci_regression(out, manifest):
    archive = P4 / "p4-evidence-ablation-review.zip"
    with zipfile.ZipFile(archive) as z:
        data = {name: z.read(name) for name in ["code/predictor.py", "code/views.py", "minimal_data/BASE_DOCUMENTS.jsonl", "minimal_data/PREDICTOR_QUERIES.jsonl", "QUERY_REGISTRY.jsonl"]}
    for name, raw in data.items():
        manifest.append({"path": str(archive.relative_to(ROOT)) + "!" + name, "sha256": sha(raw), "bytes": len(raw)})
    predictor = module("baseline_frozen_predictor", data["code/predictor.py"])
    views = module("baseline_frozen_views", data["code/views.py"])
    pilot = file_module("baseline_pilot", ROOT / "experiments/evidence_recovery_pilot/run.py")
    queries = {x["query_id"]: x for x in rows(data["minimal_data/PREDICTOR_QUERIES.jsonl"])}
    registry = {x["query_id"]: x for x in rows(data["QUERY_REGISTRY.jsonl"])}
    documents = {x["id"]: x for x in rows(data["minimal_data/BASE_DOCUMENTS.jsonl"])}
    plan = read_json(OLD / "evidence_pilot/PLAN.json")
    selected = [queries[q] for q in plan["selected_query_ids"] if queries[q]["metric"] == "CI"]
    profiles = {f: p for p, f in views.PROFILES.items() if f}
    saved = {}
    with gzip.open(OLD / "evidence_pilot/query_results.csv.gz", "rt", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            if row["metric"] == "CI" and row["policy"] in ["metric_fixed", "contract_guided"]:
                saved[(row["query_id"], row["condition"], row["policy"], int(row["budget"]))] = row

    def predict(q, visible):
        doc = json.loads(canonical(documents[q["unit"]]))
        for family in pilot.FAMILIES:
            if family not in visible:
                doc = views.project(doc, profiles[family])
        return predictor.Analyzer({q["unit"]: doc}).run(q)

    differences, checked = [], 0
    for condition, budget in [("all_nine_missing", 2), ("five_missing", 1)]:
        for q in selected:
            trajectories = {}
            for policy in ["metric_fixed", "contract_guided"]:
                visible = pilot.visible_initial(q["query_id"], condition)
                pred = predict(q, visible)
                steps = [{"budget": 0, "acquired": None, "visible": sorted(visible), "prediction": pred}]
                acquired = []
                for b in range(1, budget + 1):
                    chosen = None if pred["status"] in ["point", "not_applicable"] else pilot.choose_family(policy, q["metric"], q["protocol"], pred, visible, pilot.family_order(q["metric"]))
                    if chosen:
                        visible.add(chosen)
                        acquired.append(chosen)
                        pred = predict(q, visible)
                    steps.append({"budget": b, "acquired": chosen, "visible": sorted(visible), "prediction": pred})
                old = saved[(q["query_id"], condition, policy, budget)]
                assert old["status"] == pred["status"]
                assert old["eligibility"] == ("" if pred["eligibility"] is None else str(pred["eligibility"]))
                assert json.loads(old["acquired_order"]) == acquired
                assert json.loads(old["missing_evidence"]) == pred["missing_evidence"]
                checked += 1
                trajectories[policy] = steps
            a, b = (trajectories[p][-1]["prediction"] for p in ["metric_fixed", "contract_guided"])
            if (a["status"], a["eligibility"]) != (b["status"], b["eligibility"]):
                differences.append({"query_id": q["query_id"], "unit": q["unit"], "condition": condition, "budget": budget,
                                    "source_registry": registry[q["query_id"]], "trajectories": trajectories,
                                    "dependency_owner": "provenance", "omitted_nested_dependency": "counterfactual/**/source_object",
                                    "reason": "provenance projection recursively nulls source_object, but legacy missing_evidence only reports top-level get; fixed restores provenance, guided prioritizes receipt. This is a dependency regression, not CI truth validation."})
    counts = Counter(x["condition"] for x in differences)
    assert counts == {"all_nine_missing": 8, "five_missing": 2}, counts
    (out / "CI_8_PLUS_2_REPLAY.jsonl").write_text("".join(canonical(x) + "\n" for x in differences), encoding="utf-8")
    return {"ci_queries_replayed": len(selected), "policy_endpoint_rows_verified_against_archive": checked, "difference_counts": dict(counts), "model_calls": 0, "sandbox_executions": 0}


def hiaa_regression(out, manifest):
    path = ROOT / "tests/unit/analysis/test_hiaa_contract_repair.py"
    tests = file_module("baseline_hiaa_tests", path)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    (out / "HIAA_TEST_RESULTS.txt").write_text(stream.getvalue(), encoding="utf-8")
    assert result.wasSuccessful() and result.testsRun == 13
    contract = file_module("baseline_hiaa_contract", ROOT / "experiments/hiaa_contract_repair/contract.py")
    groups = defaultdict(list)
    raw_count = 0
    for phase in ["f", "g", "h"]:
        stage = ROOT / "datasets/t17-v2/stages" / phase
        definition = read_json(stage / "dataset-manifest.json")
        for relative in definition["tables"]["core-trials.jsonl"]:
            source = stage / relative
            raw = source.read_bytes()
            manifest.append({"path": source.relative_to(ROOT).as_posix(), "sha256": sha(raw), "bytes": len(raw)})
            for line, row in enumerate(rows(raw), 1):
                meta = (row.get("data") or {}).get("metadata", {})
                if not meta.get("hiaa_cell"):
                    continue
                failure = {"run_status": row["status"], "issues": [x.get("reason") for x in row["issues"]], "steps": [{"behavior": x.get("behavior"), "schema_valid": x.get("schema_valid")} for x in row["decisions"]]}
                key = (phase, meta["hiaa_design_id"], row["identity"]["semantic_template_id"], row["identity"]["repeat_index"])
                groups[key].append({"run_id": row["run_id"], "cell": meta["hiaa_cell"], "eligible": contract.qualification(failure), "source": source.relative_to(ROOT).as_posix() + f"#L{line}"})
                raw_count += 1
    qualified = []
    for key, group in groups.items():
        complete = len(group) == 4 and {x["cell"] for x in group} == {"p00", "p01", "p10", "p11"}
        eligible = complete and all(x["eligible"] for x in group)
        for x in group:
            qualified.append(dict(x, phase=key[0], design=key[1], quartet_eligible=eligible))
    p3r = ROOT / "论文材料/P3_机制测量/p3r-20260917-103400/legacy/HIAA_CELLS.csv"
    checks = []
    with p3r.open(encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            if row["phase"] not in ["f", "g", "h"]:
                continue
            chosen = [x for x in qualified if x["phase"] == row["phase"] and x["design"] == row["design"] and x["cell"] == row["cell"] and (row["policy"] == "scheduled" or x["quartet_eligible"])]
            ids = sorted(x["run_id"] for x in chosen)
            assert ids == sorted(json.loads(row["run_ids"])) and len(ids) == int(row["denominator"])
            checks.append({"phase": row["phase"], "design": row["design"], "policy": row["policy"], "cell": row["cell"], "exact_run_set_matches": True, "denominator": len(ids), "run_ids": ids, "raw_source_refs": [x["source"] for x in chosen]})
    assert len(checks) == 48 and raw_count == 360 and len(groups) == 90
    selected = [x for x in checks if x["phase"] in ["f", "h"] and x["design"] == "c2-tool-return-grid" and x["policy"] == "valid_only"]
    assert len(selected) == 8 and all(x["denominator"] == 13 for x in selected)
    write_csv(out / "HIAA_P3R_48_MEMBERSHIP_CHECKS.csv", checks)
    return {"tests_run": result.testsRun, "tests_passed": result.testsRun, "raw_runs": raw_count, "quartets": len(groups), "exact_membership_checks_passed": len(checks), "f_h_toolreturn_valid_only_denominators": [x["denominator"] for x in selected]}


def external_inventory(out, manifest, external_root):
    inventory = []
    paths = [ROOT / "benchmarks/clawtrojan/README.md", ROOT / "benchmarks/clawtrojan/native/UPSTREAM.json", ROOT / "benchmarks/clawtrojan/native/LICENSE", ROOT / "docs/openclaw-adapter-design.md"]
    p0 = external_root / "ClawTrojan-P0-measurement-audit-20260915-v1"
    files = ["P0_FINAL_REPORT.md", "FACTS585.json", "OBSERVED_EVENTS.jsonl", "ROW_AUDIT585.jsonl", "TASK_OBLIGATIONS39.json", "SOURCE_MAP.json", "SOURCE_HASH_CHECKS.json"]
    schemas = {}
    for name in files:
        path = p0 / name
        if path.exists():
            paths.append(path)
            if name.endswith(".jsonl"):
                data = rows(path.read_bytes())
            elif name.endswith(".json"):
                data = read_json(path)
            else:
                continue
            schemas[name] = {"records": len(data), "top_keys": sorted(data[0]) if isinstance(data, list) and data else sorted(data)}
    facts = read_json(p0 / "FACTS585.json") if (p0 / "FACTS585.json").exists() else []
    obligations = read_json(p0 / "TASK_OBLIGATIONS39.json") if (p0 / "TASK_OBLIGATIONS39.json").exists() else []
    inventory.append({"source_id": "clawtrojan_historical_p0", "files_present": bool(facts), "root": str(p0), "schema_audit": schemas,
                      "fact_records": len(facts), "observed_calls": sum(x["call_count"] for x in facts), "obligation_cards": len(obligations),
                      "independent_contract_oracle": "NOT_AVAILABLE", "status": "HISTORICAL_EVIDENCE_AVAILABLE_ORACLE_NOT_QUALIFIED",
                      "reason": "Actual local effects and mock-message records exist. P0 has no structured Grant; UEA unavailable. Task obligations and U/V labels are Codex-assisted with zero human review, missing preimages/policy boundaries and nonunique historical response bindings. Do not promote these labels to independent UEA/TaskSuccess truth.",
                      "not_reused": "No raw API requests, credentials, model drivers, or business actions executed."})
    upstream = read_json(ROOT / "benchmarks/clawtrojan/native/UPSTREAM.json")
    archive = ROOT / "benchmarks/clawtrojan/native/clawtrojan-native-snapshot.zip"
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        license_names = [x for x in names if Path(x).name.upper().startswith("LICENSE")]
        code_name = "agent_eval/sandbox/tool_dispatcher.py"
        code = z.read(code_name)
        code_text = code.decode("utf-8-sig")
        source_lines = [{"line": n, "text": line.strip()} for n, line in enumerate(code_text.splitlines(), 1) if any(t in line for t in ["def _message", "def _write", "def _edit", "mocked", "audit_log"])]
    inventory.append({"source_id": "clawtrojan_native_snapshot", "upstream_commit": upstream["commit"], "snapshot_member_count": len(names), "license": "MIT retained", "license_members": license_names,
                      "adapted_files": sorted(upstream["changes_from_pinned_upstream"]), "runtime_dependencies": "Historical requirements-lock present; no dependency installation/import of model SDK or harness run attempted.",
                      "independent_contract_oracle": "NOT_AVAILABLE", "reason": "Native source and C/P/S verdicts exist; verdict and attempted tool calls alone are not structured authorization or independent task truth.", "dispatcher_inspected": {"member": code_name, "sha256": sha(code), "relevant_lines": source_lines}})
    inventory.append({"source_id": "openclaw_t15", "evidence": "docs/openclaw-adapter-design.md", "commit": "452e734022214f5f00bdd44cae675cc467c3cd85", "independent_contract_oracle": "NOT_AVAILABLE",
                      "reason": "Historical real Gateway used official fake provider and SkillFlow safe sink. No equivalent grant matcher, provenance graph, or revocation hook; origin tags are provider-supplied. Existing receipts do not provide independent authorization/task truth."})
    for path in paths + [archive]:
        raw = path.read_bytes()
        label = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
        manifest.append({"path": label, "sha256": sha(raw), "bytes": len(raw)})
    write_json(out / "EXTERNAL_SOURCE_INVENTORY.json", {"external_source": "NOT_AVAILABLE", "qualification": "for this round's independent UEA and TaskSuccess contract oracle; external historical artifacts do exist", "sources": inventory, "new_model_calls": 0, "new_sandbox_executions": 0, "credential_files_read": 0})
    return {"external_source": "NOT_AVAILABLE", "source_candidates_audited": len(inventory), "clawtrojan_fact_records": len(facts), "clawtrojan_observed_calls": sum(x["call_count"] for x in facts), "qualification": "independent contract oracle unavailable; not absence of external records"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, default=Path("E:/Skill ＆ Harness"))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "SUMMARY.json").exists():
        raise SystemExit("Refuse to overwrite a completed audit; choose a fresh output directory")
    manifest = []
    for path in [Path(__file__), ROOT / "experiments/evidence_recovery_pilot/run.py", OLD / "evidence_pilot/PLAN.json", OLD / "evidence_pilot/query_results.csv.gz", ROOT / "tests/unit/analysis/test_hiaa_contract_repair.py", ROOT / "experiments/hiaa_contract_repair/contract.py"]:
        raw = path.read_bytes()
        manifest.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha(raw), "bytes": len(raw)})
    summary = {"ci_regression": ci_regression(out, manifest), "hiaa_regression": hiaa_regression(out, manifest), "external_source_audit": external_inventory(out, manifest, args.external_root), "python": sys.version, "repository_root": str(ROOT), "new_model_calls": 0, "new_sandbox_executions": 0, "historical_results_modified": False}
    write_json(out / "INPUT_MANIFEST.json", manifest)
    write_json(out / "SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
