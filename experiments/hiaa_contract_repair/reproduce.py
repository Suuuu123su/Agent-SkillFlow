"""Hash-bound raw-run audit and correction of the complete affected P4 slice.

Run from any directory: python -B /path/to/reproduce.py --out /new/directory
Only the Python standard library is required. No model calls or network access.
"""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from contract import CONTRACT_VERSION, qualification

ROOT = Path(__file__).resolve().parents[2]
CODE = Path(__file__).resolve().parent
P4 = ROOT / "论文材料/P4_测量证据消融/p4-20260917-123623"
P3R = ROOT / "论文材料/P3_机制测量/p3r-20260917-103400"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def opaque(value):
    return "i_" + digest(("P4-fixed-projection-v1|" + str(value)).encode())[:24]


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_rows(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical(x) + "\n" for x in values), encoding="utf-8")


def write_csv(path, values):
    values = list(values)
    fields = list(dict.fromkeys(k for v in values for k in v))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows({k: canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in values)


def semantic(result):
    return {k: result.get(k) for k in ["eligibility", "status", "value", "lower", "upper", "reason", "details"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        raise SystemExit("Refusing to overwrite an existing result directory: " + str(out))
    out.mkdir(parents=True)
    manifest = []

    def bind(path):
        raw = path.read_bytes()
        manifest.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(raw), "bytes": len(raw)})
        return raw

    for path in sorted(CODE.glob("*.py")):
        bind(path)
    for name in ["predictor.py", "views.py", "ingest.py"]:
        bind(P4 / "code" / name)
    spec = importlib.util.spec_from_file_location("frozen_hiaa_views", P4 / "code/views.py")
    views = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(views)
    queries = [x for x in map(json.loads, bind(P4 / "minimal_data/PREDICTOR_QUERIES.jsonl").splitlines()) if x["metric"] == "HIAA_run"]
    ids = {q["query_id"] for q in queries}
    registry = {x["query_id"]: x for x in map(json.loads, bind(P4 / "QUERY_REGISTRY.jsonl").splitlines()) if x["query_id"] in ids}
    archive_path = P4 / "p4-evidence-ablation-review.zip"
    bind(archive_path)
    archive = zipfile.ZipFile(archive_path)
    base_raw = archive.read("minimal_data/BASE_DOCUMENTS.jsonl")
    manifest.append({"path": str(archive_path.relative_to(ROOT)) + "!minimal_data/BASE_DOCUMENTS.jsonl", "sha256": digest(base_raw), "bytes": len(base_raw)})
    base = {x["id"]: x for x in map(json.loads, base_raw.splitlines())}
    needed = {q["unit"] for q in queries}
    for uid in list(needed):
        needed.update(x["unit"] for x in base[uid]["design"]["members"])
    documents = {uid: base[uid] for uid in sorted(needed)}
    del base, base_raw
    raw_runs = []
    raw_groups = defaultdict(list)
    for phase in ["f", "g", "h"]:
        stage = ROOT / "datasets/t17-v2/stages" / phase
        dataset_manifest = json.loads(bind(stage / "dataset-manifest.json"))
        for relative in dataset_manifest["tables"]["core-trials.jsonl"]:
            path = stage / relative
            raw_file = bind(path)
            for line_number, line in enumerate(raw_file.splitlines(), 1):
                run = json.loads(line)
                meta = (run.get("data") or {}).get("metadata", {})
                if not meta.get("hiaa_cell"):
                    continue
                uid = opaque(run["run_id"])
                document = documents[uid]
                # Bind qualifications to facts, never to old behavior_valid labels.
                expected_failure = {
                    "steps": [{"behavior": x.get("behavior"), "schema_valid": x.get("schema_valid")} for x in run["decisions"]],
                    "issues": [x.get("reason") for x in run["issues"]],
                }
                assert document["failure"] == expected_failure, run["run_id"]
                assert document["observation"]["closed"] == (run["status"] == "completed")
                document["failure"]["run_status"] = run["status"]
                old_valid = all(x.get("schema_valid") is not False and x.get("behavior") not in ["schema_rejection", "infrastructure_invalid"] for x in run["decisions"])
                new_valid = qualification(document["failure"])
                row = {
                    "phase": phase, "design": meta["hiaa_design_id"], "cluster": run["identity"]["semantic_template_id"],
                    "repeat": run["identity"]["repeat_index"], "cell": meta["hiaa_cell"],
                    "run_id": run["run_id"], "opaque_unit": uid, "run_status": run["status"],
                    "behaviors": [x.get("behavior") for x in run["decisions"]], "issues": run["issues"],
                    "old_run_eligible": old_valid, "corrected_run_eligible": new_valid,
                    "source_ref": path.relative_to(ROOT).as_posix() + f"#L{line_number}",
                    "source_file_sha256": digest(raw_file), "source_line_sha256": digest(line),
                }
                raw_runs.append(row)
                raw_groups[(phase, row["design"], row["cluster"], row["repeat"])].append(row)
    assert len(raw_runs) == len(needed) - len({q["unit"] for q in queries}) == 360
    quartets = []
    for key, group in raw_groups.items():
        complete = len(group) == 4 and {x["cell"] for x in group} == {"p00", "p01", "p10", "p11"}
        old = complete and all(x["old_run_eligible"] for x in group)
        new = complete and all(x["corrected_run_eligible"] for x in group)
        invalid = [x["run_id"] for x in group if not x["corrected_run_eligible"]]
        for row in group:
            row.update(old_quartet_eligible=old, corrected_quartet_eligible=new, excluded_due_to_runs=invalid)
        quartets.append(dict(zip(["phase", "design", "cluster", "repeat"], key), complete=complete,
                             old_eligible=old, corrected_eligible=new,
                             invalid_runs=invalid, run_ids=[x["run_id"] for x in group]))
    write_csv(out / "RUN_QUALIFICATION_AUDIT.csv", raw_runs)
    write_csv(out / "QUARTET_QUALIFICATION_AUDIT.csv", quartets)
    write_rows(out / "inputs/CORRECTED_HIAA_DOCUMENTS.jsonl", documents.values())
    write_rows(out / "inputs/HIAA_QUERIES.jsonl", queries)
    write_rows(out / "inputs/HIAA_QUERY_REGISTRY.jsonl", registry.values())
    predictions = {}
    for vid in views.PROFILES:
        view = out / ".work" / vid
        view.mkdir(parents=True)
        write_rows(view / "DOCUMENTS.jsonl", (views.project(x, vid) for x in documents.values()))
        projected_queries = [dict(views.project(q, vid), query_id=q["query_id"]) for q in queries]
        write_rows(view / "QUERIES.jsonl", projected_queries)
        (out / "results").mkdir(exist_ok=True)
        (out / "audit").mkdir(exist_ok=True)
        subprocess.run([sys.executable, "-B", str(CODE / "predict.py"), str(view),
                        str(P4 / "code/predictor.py"), str(out / "results" / (vid + ".jsonl")),
                        str(out / "audit" / (vid + ".json"))], check=True)
        predictions[vid] = {x["query_id"]: x for x in rows(out / "results" / (vid + ".jsonl"))}
        print("Predicted", vid, len(predictions[vid]), flush=True)
    shutil.rmtree(out / ".work")
    # References and archived outputs are opened only after predictions are sealed.
    old_predictions = {}
    for vid in views.PROFILES:
        raw = archive.read("results/" + vid + ".jsonl")
        manifest.append({"path": str(archive_path.relative_to(ROOT)) + "!results/" + vid + ".jsonl", "sha256": digest(raw), "bytes": len(raw)})
        old_predictions[vid] = {x["query_id"]: x for x in map(json.loads, raw.splitlines()) if x["query_id"] in ids}
    p3r_path = P3R / "legacy/HIAA_CELLS.csv"
    bind(p3r_path)
    p3r_cells = list(csv.DictReader(p3r_path.open(encoding="utf-8-sig")))
    membership_checks = []
    for cell in p3r_cells:
        if cell["phase"] not in ["f", "g", "h"]:
            continue
        selected = [r for r in raw_runs if r["phase"] == cell["phase"] and r["design"] == cell["design"] and r["cell"] == cell["cell"] and (cell["policy"] == "scheduled" or r["corrected_quartet_eligible"])]
        match = sorted(r["run_id"] for r in selected) == sorted(json.loads(cell["run_ids"]))
        assert match and len(selected) == int(cell["denominator"]), cell
        membership_checks.append({"phase": cell["phase"], "design": cell["design"], "policy": cell["policy"], "cell": cell["cell"], "exact_run_set_matches": match, "denominator": len(selected)})
    diffs, cell_rows, contrasts, summary_rows, downstream = [], [], [], [], []
    for vid in views.PROFILES:
        for q in queries:
            qid = q["query_id"]
            old, new, reg = old_predictions[vid][qid], predictions[vid][qid], registry[qid]
            metadata = {"view_id": vid, "query_id": qid, "phase": reg["phase"], "design": reg["native_unit_ref"], "protocol": q["protocol"]}
            changed = [k for k in semantic(old) if semantic(old)[k] != semantic(new)[k]]
            diffs.append(dict(metadata, changed_fields=changed, old=semantic(old), corrected=semantic(new)))
            if q["protocol"] == "scheduled":
                assert semantic(new) == semantic(old), (vid, qid, "scheduled drift")
            if vid == "V09" and q["protocol"] == "valid_only":
                assert new["eligibility"] is None and new["status"] == "unknown"
                assert new["reason"] == "valid_only_qualification_unknown"
            if vid in ["V11", "V12"]:
                assert semantic(new) == semantic(predictions["V00"][qid]), (vid, qid, "negative control")
            contrasts.append(dict(metadata, **{k: new[k] for k in ["eligibility", "status", "value", "lower", "upper", "reason"]}, sampling_interval=new["details"].get("sampling_interval")))
            for name, cell in new["details"]["cells"].items():
                cell_rows.append(dict(metadata, cell=name, **cell))
        for phase in ["f", "g", "h"]:
            for protocol in ["scheduled", "valid_only"]:
                members = [q["query_id"] for q in queries if registry[q["query_id"]]["phase"] == phase and q["protocol"] == protocol]
                before, after = [], []
                for source, target in [(old_predictions[vid], before), (predictions[vid], after)]:
                    rr = [source[qid] for qid in members]
                    target.append({"fixed_queries": len(rr), "statuses": dict(Counter(x["status"] for x in rr)), "eligibility": dict(Counter(str(x["eligibility"]) for x in rr)), "numeric_sum": sum(x["value"] for x in rr if x["status"] == "point"), "numeric_point_n": sum(x["status"] == "point" for x in rr)})
                assert before == after, "Unexpected main-summary change"
                downstream.append({"view_id": vid, "phase": phase, "protocol": protocol, "summary_unchanged": True, "summary": after[0]})
    for vid in views.PROFILES:
        for q in queries:
            qid = q["query_id"]
            before = [old_predictions[x][qid][k] for x in ["V00", vid] for k in ["status", "eligibility"]]
            after = [predictions[x][qid][k] for x in ["V00", vid] for k in ["status", "eligibility"]]
            assert before == after, "Unexpected full-to-view transition change"
    for row in cell_rows:
        if row["view_id"] != "V00":
            continue
        expected = next(x for x in p3r_cells if (x["phase"], x["design"], x["policy"], x["cell"]) == (row["phase"], row["design"], row["protocol"], row["cell"]))
        assert row["denominator"] == int(expected["denominator"]) and row["true"] == int(expected["numerator"])
    changed = [x for x in diffs if x["changed_fields"]]
    assert len(changed) == 24
    summary = {
        "contract_version": CONTRACT_VERSION, "raw_grid_runs": len(raw_runs), "quartets": len(quartets),
        "changed_quartets": sum(x["old_eligible"] != x["corrected_eligible"] for x in quartets),
        "non_normal_runs_explaining_conflict": sum(x["old_run_eligible"] != x["corrected_run_eligible"] for x in raw_runs),
        "queries": len(queries), "views": 13, "predictions": sum(map(len, predictions.values())),
        "changed_predictions": len(changed), "changed_top_level_point_values": sum(x["old"]["value"] != x["corrected"]["value"] for x in diffs),
        "changed_cell_rows": sum(old_predictions[v][q]["details"]["cells"][c] != predictions[v][q]["details"]["cells"][c] for v in predictions for q in ids for c in ["p00", "p01", "p10", "p11"]),
        "p3r_exact_run_set_matches": len(membership_checks), "scheduled_predictions_unchanged": 78,
        "failure_withheld_valid_only_unknown": 6, "negative_control_differences": 0,
        "main_summary_differences": 0, "full_to_view_transition_differences": 0,
        "non_hiaa_metric_code_changed": False, "full_252096_prediction_sweep_rerun": False,
        "model_calls": 0, "business_tool_calls": 0, "network_calls": 0,
        "status": "PASS_OFFLINE_CORRECTION", "tests": "See TEST_RESULTS.txt (separate targeted test invocation).",
    }
    write_csv(out / "HIAA_CELLS_CORRECTED.csv", cell_rows)
    write_csv(out / "HIAA_CONTRASTS_CORRECTED.csv", contrasts)
    write_rows(out / "HIAA_RESULT_DIFFS.jsonl", diffs)
    write_csv(out / "P3R_EXACT_MEMBERSHIP_CHECKS.csv", membership_checks)
    write_rows(out / "DOWNSTREAM_SUMMARY_CHECKS.jsonl", downstream)
    write_json(out / "SUMMARY.json", summary)
    write_json(out / "INPUT_MANIFEST.json", {"contract_version": CONTRACT_VERSION, "sources": manifest})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
