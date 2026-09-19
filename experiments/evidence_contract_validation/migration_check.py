"""Read-only historical dependency migration; never regenerates prior outcomes."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import types
import zipfile
from pathlib import Path

from .dependencies import CHANNELS, VERSION, build_ledger, project


def changed_paths(before, after, path=""):
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict) and before.keys() == after.keys():
        return [p for key in before for p in changed_paths(
            before[key], after[key], path + "/" + key.replace("~", "~0").replace("/", "~1"))]
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [p for index, value in enumerate(before) for p in changed_paths(
            value, after[index], path + "/" + str(index))]
    return [path]


def check(repo_root):
    root = Path(repo_root)
    prior = root / "论文材料/修复与补强_20260919"
    archive = root / "论文材料/P4_测量证据消融/p4-20260917-123623/p4-evidence-ablation-review.zip"
    with zipfile.ZipFile(archive) as source:
        members = {name: source.read(name) for name in (
            "code/predictor.py", "code/views.py", "minimal_data/BASE_DOCUMENTS.jsonl",
            "minimal_data/PREDICTOR_QUERIES.jsonl")}

    def rows(name):
        return [json.loads(line) for line in members[name].decode("utf-8-sig").splitlines() if line]

    documents = {row["id"]: row for row in rows("minimal_data/BASE_DOCUMENTS.jsonl")}
    queries = {row["query_id"]: row for row in rows("minimal_data/PREDICTOR_QUERIES.jsonl")}
    predictor = types.ModuleType("frozen_m0_predictor")
    views = types.ModuleType("frozen_m0_views")
    exec(compile(members["code/predictor.py"], "<frozen-p4-predictor>", "exec"), predictor.__dict__)
    exec(compile(members["code/views.py"], "<frozen-p4-views>", "exec"), views.__dict__)
    profiles = {channel: profile for profile, channel in views.PROFILES.items() if channel}

    def state(prediction):
        return {key: prediction[key] for key in ("status", "eligibility", "value", "lower", "upper")}

    full_reports, selected_units = [], set()
    for directory, expected_count in (("evidence_pilot", 240), ("evidence_pilot_reference", 235)):
        plan = json.loads((prior / directory / "PLAN.json").read_text("utf-8"))
        ids = plan["selected_query_ids"]
        if len(ids) != expected_count:
            raise ValueError("Historical development selection changed")
        differences = []
        for query_id in ids:
            query = queries[query_id]
            selected_units.add(query["unit"])
            document = documents[query["unit"]]
            old = predictor.Analyzer({query["unit"]: document}).run(query)
            new = predictor.Analyzer({query["unit"]: project(document, CHANNELS)}).run(query)
            if state(old) != state(new):
                differences.append({"query_id": query_id, "old": state(old), "new": state(new)})
        full_reports.append({"development_source": directory, "queries": len(ids),
                             "full_state_differences": differences,
                             "status": "PASS" if not differences else "FAIL"})
    masks = {channel: {"documents_with_projection_change": 0, "changed_path_examples": []}
             for channel in CHANNELS}
    unknown_owners, controlled_path_count, checked_projection_count = [], 0, 0
    for unit in sorted(selected_units):
        document = documents[unit]
        entries = {entry["path"]: entry for entry in build_ledger(document)["entries"]}
        controlled_path_count += len(entries)
        for channel in CHANNELS:
            old = views.project(copy.deepcopy(document), profiles[channel])
            new = project(document, set(CHANNELS) - {channel})
            checked_projection_count += 1
            for path in changed_paths(document, new):
                if path not in entries or entries[path]["owner"] not in CHANNELS:
                    unknown_owners.append({"unit": unit, "hidden_channel": channel, "path": path})
            changed = changed_paths(old, new)
            if changed:
                masks[channel]["documents_with_projection_change"] += 1
                if len(masks[channel]["changed_path_examples"]) < 5:
                    masks[channel]["changed_path_examples"].append({"unit": unit, "paths": changed[:8]})
    return {
        "dependency_contract_version": VERSION,
        "status": "PASS" if not unknown_owners and all(row["status"] == "PASS" for row in full_reports) else "FAIL",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "frozen_member_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in members.items()},
        "full_migration": full_reports,
        "unique_historical_documents": len(selected_units),
        "controlled_concrete_paths": controlled_path_count,
        "single_channel_projections_checked": checked_projection_count,
        "unregistered_changed_paths": unknown_owners,
        "versioned_projection_differences": masks,
        "new_business_executions": 0, "model_calls": 0,
        "scope": "Historical development observations only; 240 and 235 selections overlap. Full is the same predictor comparator, not independent truth.",
        "migration_notes": [
            "The historical files and predictor remain unchanged.",
            "Failure qualification/completeness mirrors are now masked in every layout.",
            "Lifecycle grant times and revocations, and scope grant limits, require grant visibility.",
            "Session and scope/lifetime mirrors require their owner channel wherever carried by a channel.",
            "Capability initial state is conservatively hidden with grant; capability metrics remain out of scope.",
            "Every cross-field restoration is an explicit chargeable patch with concrete dependency atoms.",
            "Historical CI 8+2 trajectory reproduction is reported separately in the baseline source audit.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check(args.repo_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps({key: report[key] for key in (
        "status", "unique_historical_documents", "controlled_concrete_paths",
        "single_channel_projections_checked", "unregistered_changed_paths")},
        ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

