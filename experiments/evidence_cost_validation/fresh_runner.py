"""Versioned orthogonal authorization/execution runner; old supervisor logic copied unchanged.

Only schedule variant and worker variant selection are separated. Persistent
state, actual worker operations, adapter and independent oracle stay frozen.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from experiments.evidence_contract_validation.sandbox import (
    WORKTREE_ROOT,SOURCE_ID,load_registry,snapshot,_write_new,_append,_initialize,
    _schedule as original_schedule,_worker as original_worker)


def _schedule(spec):
    return original_schedule(spec | {'variant':spec['grant_variant']})


def run_unit(spec: dict[str, Any], raw_root: str | Path, attempt_id: str,
             timeout_seconds: float = 10.0) -> dict[str, Any]:
    """Run ONE counted logical-unit attempt; never retries or replaces files."""
    raw_root = Path(raw_root).resolve()
    if WORKTREE_ROOT not in raw_root.parents or raw_root.drive.upper() == "C:":
        raise ValueError("raw_root must be inside the authorized E-drive worktree")
    for label in (spec["execution_unit_id"], attempt_id):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", label):
            raise ValueError("unsafe unit or attempt identifier")
    spec = {**spec, "_attempt_id": attempt_id, "_effect_id": f"effect:{spec['execution_unit_id']}:{attempt_id}"}
    directory = raw_root / spec["execution_unit_id"] / attempt_id
    directory.mkdir(parents=True, exist_ok=False)
    sandbox_dir = directory / "sandbox"
    sandbox_dir.mkdir()
    _write_new(directory / "spec.json", spec)
    journal = directory / "supervisor.jsonl"
    _append(journal, {"event": "attempt_registered", "attempt_id": attempt_id,
                      "execution_unit_id": spec["execution_unit_id"], "time_ns": time.monotonic_ns()})
    # Initialization is counted within this attempt and precedes its action boundary.
    _initialize(spec, sandbox_dir)
    before = snapshot(sandbox_dir)
    _write_new(directory / "before.json", before)
    schedule = _schedule(spec)
    _write_new(directory / "permission_schedule.json", schedule)
    _write_new(directory / "task_requirements.json", spec["task_requirements"])
    started = time.monotonic_ns()
    _append(journal, {"event": "action_started", "time_ns": started,
                      "action": spec["action"], "resource": spec["resource"],
                      "session_id": spec["session_id"], "task_id": spec["task_id"]})
    worker_tmp = directory / "worker_tmp"
    worker_tmp.mkdir()
    # Allowlist startup variables only; never fetch or inherit credential variables.
    worker_env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "PATH") if name in os.environ}
    worker_env.update(TEMP=str(worker_tmp), TMP=str(worker_tmp), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    timed_out = False
    try:
        process = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--worker",
                                  str(directory / "spec.json"), str(sandbox_dir)],
                                 capture_output=True, timeout=timeout_seconds, check=False,
                                 cwd=sandbox_dir, env=worker_env)
        returncode = process.returncode
        stdout = process.stdout.decode("utf-8", errors="replace")
        stderr = process.stderr.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as error:
        timed_out, returncode = True, None
        stdout = (error.stdout or b"").decode("utf-8", errors="replace")
        stderr = "supervised_worker_timeout"
    finished = time.monotonic_ns()
    after = snapshot(sandbox_dir)
    _write_new(directory / "after.json", after)
    changes = [{"path": path, "before_sha256": before.get(path, {}).get("sha256"),
                "after_sha256": after.get(path, {}).get("sha256")}
               for path in sorted(set(before) | set(after))
               if before.get(path, {}).get("sha256") != after.get(path, {}).get("sha256")]
    receipt = None
    if stdout.strip():
        try:
            receipt = json.loads(stdout)
        except json.JSONDecodeError:
            stderr += "\ninvalid_collector_ack"
    complete = not timed_out
    effect_id = f"effect:{spec['execution_unit_id']}:{attempt_id}"
    _append(journal, {"event": "action_joined", "time_ns": finished, "returncode": returncode,
                      "timed_out": timed_out, "changes": changes,
                      "snapshot_complete": complete, "effect_id": effect_id})
    record = {
        "schema_version": "independent-sandbox-raw-v1", "source_id": SOURCE_ID,
        "execution_unit_id": spec["execution_unit_id"], "family_id": spec["family_id"],
        "split": spec["split"], "construct": spec["construct"], "operation": spec["operation"],
        "task_id": spec["task_id"], "session_id": spec["session_id"], "attempt_id": attempt_id,
        "attempt": {"action": spec["action"], "resource": spec["resource"],
                    "task_id": spec["task_id"], "session_id": spec["session_id"],
                    "started_ns": started, "finished_ns": finished, "effect_id": effect_id, "attempt_id": attempt_id},
        "permission_schedule": schedule, "task_requirements": spec["task_requirements"],
        "supervisor": {"complete": complete, "effect_id": effect_id,
                       "committed_effect": bool(changes), "state_before": before,
                       "state_after": after, "side_effect_records": changes,
                       "process_returncode": returncode, "timed_out": timed_out,
                       "effect_semantics": load_registry()["effect_semantics"]},
        "collector": {"receipt": receipt, "acknowledgment_lost": bool(changes) and receipt is None,
                      "stdout": stdout, "stderr": stderr},
        "isolation": "cooperative-input-isolation; worker and supervisor share OS identity",
    }
    _write_new(directory / "record.json", record)
    return record

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--worker':
        spec=json.loads(Path(sys.argv[2]).read_text('utf-8'))
        original_worker(spec | {'variant':spec['execution_variant']},Path(sys.argv[3]).resolve())
    else:raise SystemExit('Use the budgeted fresh controller')
