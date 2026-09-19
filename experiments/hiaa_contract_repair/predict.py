"""Isolated offline HIAA prediction; no raw run table, old labels or outputs."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

from contract import corrected_analyzer


def main():
    view, frozen, output, audit_path = map(lambda x: Path(x).resolve(), sys.argv[1:5])
    spec = importlib.util.spec_from_file_location("frozen_hiaa_predictor", frozen)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    analyzer_class = corrected_analyzer(module.Analyzer)
    accesses = []

    def audit(event, args):
        if event.startswith(("socket.", "subprocess.", "os.system")):
            raise RuntimeError("HIAA_OFFLINE_PROCESS_NETWORK_DENIED")
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            mode, flags = str(args[1] or ""), args[2] or 0
            write = any(x in mode for x in "wax+") or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)
            allowed = path in [output, audit_path] if write else path in [
                view / "DOCUMENTS.jsonl", view / "QUERIES.jsonl"
            ]
            if not allowed:
                raise RuntimeError("HIAA_OUTSIDE_PROJECTED_VIEW: " + str(path))
            accesses.append({"file": path.name, "operation": "write" if write else "read"})

    sys.addaudithook(audit)
    documents_raw = (view / "DOCUMENTS.jsonl").read_bytes()
    queries_raw = (view / "QUERIES.jsonl").read_bytes()
    documents = {x["id"]: x for x in map(json.loads, documents_raw.splitlines())}
    queries = list(map(json.loads, queries_raw.splitlines()))
    analyzer = analyzer_class(documents)
    with output.open("x", encoding="utf-8") as stream:
        for query in queries:
            stream.write(json.dumps(analyzer.run(query), ensure_ascii=False, sort_keys=True) + "\n")
    audit_path.write_text(json.dumps({
        "documents_sha256": hashlib.sha256(documents_raw).hexdigest(),
        "queries_sha256": hashlib.sha256(queries_raw).hexdigest(),
        "queries": len(queries), "documents": len(documents), "accesses": accesses,
        "network_calls": 0, "business_tool_calls": 0, "model_calls": 0,
        "reference_or_old_prediction_reads": 0,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
