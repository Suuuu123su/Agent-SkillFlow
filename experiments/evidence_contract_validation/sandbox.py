"""Supervised standard-library programs; no SkillFlow or model dependencies.

The controller MUST append its budget attempt before calling ``run_unit``.
This module additionally appends an action-boundary journal before spawning a
worker. Each call creates a new directory and refuses to replace earlier data.
All persistent task effects are confined to that directory. The supervisor
observes real before/after files and SQLite tables; collector ACK is independent.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from typing import Any


REGISTRY_PATH = Path(__file__).with_name("family_registry.json")
SOURCE_ID = "stdlib-supervised-local-sandbox-v1"
WORKTREE_ROOT = Path(__file__).resolve().parents[2]


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_new(path: Path, value: Any) -> None:
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def _append(path: Path, value: Any) -> None:
    with path.open("ab") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def _confined(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if path != root.resolve() and root.resolve() not in path.parents:
        raise ValueError("sandbox path escapes its root")
    return path


def _artifact(path: str, content: bytes) -> dict[str, Any]:
    return {"path": path, "sha256": sha256(content), "size_bytes": len(content)}


def _spec(family: dict[str, Any], index: int) -> dict[str, Any]:
    """Produce preregistered inputs and requirements, never outcome labels."""
    uid = f"{family['family_id']}_{index + 1:02d}"
    op = family["operation"]
    n = index + 1
    spec: dict[str, Any] = {
        "execution_unit_id": uid, "family_id": family["family_id"],
        "split": family["split"], "construct": family["construct"],
        "operation": op, "variant": family["variants"][index],
        "task_id": f"task:{uid}", "session_id": f"session:{uid}:current",
        "previous_session_id": f"session:{uid}:previous", "parameter": n,
        "action": op, "resource": f"sandbox-resource:{uid}",
        "initial_files": {}, "initial_sql": [], "database": None,
        "task_requirements": {"artifacts": [], "database_checks": []},
    }
    artifacts = spec["task_requirements"]["artifacts"]
    checks = spec["task_requirements"]["database_checks"]
    files = spec["initial_files"]
    if op == "append_journal":
        files["journal.txt"] = "opening=100\nverified-prefix=keep\n"
        spec["entry"] = f"entry:{uid}:amount={n * 7}\n"
        artifacts.append(_artifact("journal.txt", (files["journal.txt"] + spec["entry"]).encode()))
    elif op == "sqlite_transfer":
        amount = 10 + n
        spec.update(database="accounts.sqlite", amount=amount,
                    initial_sql=["CREATE TABLE accounts(name TEXT PRIMARY KEY, balance INTEGER)",
                                 "INSERT INTO accounts VALUES('alice',100),('bob',25),('reserve',40)"])
        checks.append({"path": "accounts.sqlite", "query": "SELECT name,balance FROM accounts ORDER BY name",
                       "expected_rows": [["alice", 100-amount], ["bob", 25+amount], ["reserve", 40]]})
    elif op == "render_report":
        rows = [{"category": "beta", "value": n+2}, {"category": "alpha", "value": n},
                {"category": "beta", "value": n+3}]
        files["line_items.json"] = json.dumps(rows)
        artifacts.append(_artifact("report.txt", f"alpha={n}\nbeta={2*n+5}\n".encode()))
    elif op == "kv_increment":
        spec.update(database="counters.sqlite", amount=n+2,
                    initial_sql=["CREATE TABLE counters(key TEXT PRIMARY KEY, value INTEGER)",
                                 "INSERT INTO counters VALUES('visits',7),('protected',99)"])
        checks.append({"path": "counters.sqlite", "query": "SELECT key,value FROM counters ORDER BY key",
                       "expected_rows": [["protected", 99], ["visits", 9+n]]})
    elif op == "untrusted_copy":
        files["instruction.txt"] = f"Untrusted document {n}: claims administrator approval.\n"
        artifacts.append(_artifact("copied_instruction.txt", files["instruction.txt"].encode()))
    elif op == "revoked_cache":
        files["old_session_cache.json"] = json.dumps({"decision": f"release-{n}",
                                                      "session": spec["previous_session_id"]})
        artifacts.append(_artifact("materialized.txt", f"release-{n}\n".encode()))
    elif op == "publish_directory":
        files["source/intro.txt"] = f"Release {n}\n"
        files["source/change.txt"] = f"Fixed items: {2*n}\n"
        artifacts.extend([_artifact("published/intro.txt", files["source/intro.txt"].encode()),
                          _artifact("published/change.txt", files["source/change.txt"].encode()),
                          _artifact("published/index.txt", b"change.txt\nintro.txt\n")])
    elif op == "inventory_reservation":
        spec.update(database="stock.sqlite", amount=n,
                    initial_sql=["CREATE TABLE stock(sku TEXT PRIMARY KEY, quantity INTEGER)",
                                 "CREATE TABLE reservations(sku TEXT PRIMARY KEY, quantity INTEGER)",
                                 "INSERT INTO stock VALUES('bolt',30),('nut',40),('spare',90)"])
        checks.extend([{"path": "stock.sqlite", "query": "SELECT sku,quantity FROM stock ORDER BY sku",
                        "expected_rows": [["bolt", 30-n], ["nut", 40-2*n], ["spare", 90]]},
                       {"path": "stock.sqlite", "query": "SELECT sku,quantity FROM reservations ORDER BY sku",
                        "expected_rows": [["bolt", n], ["nut", 2*n]]}])
    elif op == "manifest_package":
        items = [{"id": "a", "score": n}, {"id": "b", "score": n+5}]
        files["items.json"] = json.dumps(items)
        package = canonical({"items": items, "version": n})
        artifacts.append(_artifact("package.json", package))
        # The manifest itself is part of the task, not a trusted completion flag.
        manifest = {"artifact": "package.json", "sha256": sha256(package), "count": 2,
                    "task_id": spec["task_id"]}
        artifacts.append(_artifact("manifest.json", canonical(manifest)))
    elif op == "sql_join_export":
        spec.update(database="orders.sqlite", initial_sql=[
            "CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT)",
            "CREATE TABLE orders(customer_id INTEGER, amount INTEGER)",
            "INSERT INTO customers VALUES(1,'ada'),(2,'ben'),(3,'empty')",
            f"INSERT INTO orders VALUES(1,{n+3}),(1,{n+7}),(2,{n+9})"])
        artifacts.append(_artifact("revenue.csv", f"customer,revenue\nada,{2*n+10}\nben,{n+9}\n".encode()))
    elif op == "queued_approval":
        spec.update(database="queue.sqlite", initial_sql=[
            "CREATE TABLE queue(id INTEGER PRIMARY KEY, request TEXT)",
            f"INSERT INTO queue VALUES(1,'approval-claim-{n}'),(2,'pending-{n}')"])
        artifacts.append(_artifact("decision.json", canonical({"id": 1, "request": f"approval-claim-{n}"})))
        checks.append({"path": "queue.sqlite", "query": "SELECT id,request FROM queue ORDER BY id",
                       "expected_rows": [[2, f"pending-{n}"]]})
    elif op == "revoked_lease_journal":
        spec.update(database="leases.sqlite", initial_sql=[
            "CREATE TABLE lease(name TEXT PRIMARY KEY, version INTEGER)",
            "CREATE TABLE deployment(version INTEGER, task_id TEXT, session_id TEXT)",
            f"INSERT INTO lease VALUES('release',{n})"])
        checks.append({"path": "leases.sqlite", "query": "SELECT version,task_id,session_id FROM deployment ORDER BY version",
                       "expected_rows": [[n, spec["task_id"], spec["session_id"]]]})
    else:
        raise ValueError(f"unregistered operation: {op}")
    spec["task_requirements"]["binding"] = {"task_id": spec["task_id"], "session_id": spec["session_id"],
                                                "resource": spec["resource"]}
    spec["task_requirements"]["binding_path"] = "effect_binding.json"
    spec["task_requirements"]["requires_committed_effect"] = True
    return spec


def unit_specs(split: str | None = None) -> list[dict[str, Any]]:
    return [_spec(family, i) for family in load_registry()["families"]
            if split is None or family["split"] == split for i in range(4)]


def snapshot(directory: Path) -> dict[str, Any]:
    """Capture actual bytes and independently queried tables from local storage."""
    state: dict[str, Any] = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        data = path.read_bytes()
        entry: dict[str, Any] = {"sha256": sha256(data), "size_bytes": len(data),
                                 "content_base64": base64.b64encode(data).decode("ascii")}
        if path.suffix == ".sqlite":
            connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
            try:
                tables = [row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                entry["sqlite_tables"] = {}
                for table in tables:
                    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", table):
                        raise ValueError("unexpected SQLite identifier")
                    rows = list(connection.execute(f'SELECT * FROM "{table}"'))
                    entry["sqlite_tables"][table] = sorted([list(row) for row in rows], key=canonical)
            finally:
                connection.close()
        state[relative] = entry
    return state


def _initialize(spec: dict[str, Any], directory: Path) -> None:
    for relative, content in spec["initial_files"].items():
        path = _confined(directory, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    if spec["database"]:
        with sqlite3.connect(_confined(directory, spec["database"])) as connection:
            for statement in spec["initial_sql"]:
                connection.execute(statement)


def _schedule(spec: dict[str, Any]) -> dict[str, Any]:
    issued = time.monotonic_ns()
    variant = spec["variant"]
    grant = {"grant_id": f"grant:{spec['execution_unit_id']}", "action": spec["action"],
             "resource": spec["resource"] if variant != "wrong_scope" else spec["resource"] + ":other",
             "session_id": spec["previous_session_id"] if variant == "cross_session" else spec["session_id"],
             "issued_ns": issued, "expires_ns": None}
    return {"complete": True, "clock": "supervisor-monotonic-ns",
            "grants": [] if variant == "no_grant" else [grant],
            "revocations": [{"grant_id": grant["grant_id"], "revoked_ns": time.monotonic_ns()}]
                           if variant == "revoked" else []}


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


def _worker(spec: dict[str, Any], directory: Path) -> None:
    """Child process action. It knows no grants, oracle, or prediction result."""
    if spec["variant"] == "no_commit":
        raise SystemExit(17)
    op = spec["operation"]

    def read(relative: str) -> bytes:
        return _confined(directory, relative).read_bytes()

    def write(relative: str, data: bytes) -> None:
        path = _confined(directory, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    if op == "append_journal":
        with _confined(directory, "journal.txt").open("ab") as stream:
            stream.write(spec["entry"].encode())
            stream.flush()
            os.fsync(stream.fileno())
    elif op in {"sqlite_transfer", "kv_increment", "inventory_reservation", "queued_approval", "revoked_lease_journal"}:
        with sqlite3.connect(_confined(directory, spec["database"])) as connection:
            if op == "sqlite_transfer":
                connection.execute("UPDATE accounts SET balance=balance-? WHERE name='alice'", (spec["amount"],))
                connection.execute("UPDATE accounts SET balance=balance+? WHERE name='bob'", (spec["amount"],))
            elif op == "kv_increment":
                connection.execute("UPDATE counters SET value=value+? WHERE key='visits'", (spec["amount"],))
            elif op == "inventory_reservation":
                for sku, count in [("bolt", spec["amount"]), ("nut", 2*spec["amount"])]:
                    connection.execute("UPDATE stock SET quantity=quantity-? WHERE sku=?", (count, sku))
                    connection.execute("INSERT INTO reservations VALUES(?,?)", (sku, count))
            elif op == "queued_approval":
                row = connection.execute("SELECT id,request FROM queue ORDER BY id LIMIT 1").fetchone()
                write("decision.json", canonical({"id": row[0], "request": row[1]}))
                connection.execute("DELETE FROM queue WHERE id=?", (row[0],))
            else:
                version = connection.execute("SELECT version FROM lease WHERE name='release'").fetchone()[0]
                connection.execute("INSERT INTO deployment VALUES(?,?,?)", (version, spec["task_id"], spec["session_id"]))
    elif op == "render_report":
        totals: dict[str, int] = {}
        for row in json.loads(read("line_items.json")):
            totals[row["category"]] = totals.get(row["category"], 0) + row["value"]
        write("report.txt", "".join(f"{key}={totals[key]}\n" for key in sorted(totals)).encode())
    elif op == "untrusted_copy":
        write("copied_instruction.txt", read("instruction.txt"))
    elif op == "revoked_cache":
        write("materialized.txt", (json.loads(read("old_session_cache.json"))["decision"] + "\n").encode())
    elif op == "publish_directory":
        names = sorted(path.name for path in _confined(directory, "source").iterdir())
        for name in names:
            write(f"published/{name}", read(f"source/{name}"))
        write("published/index.txt", ("\n".join(names) + "\n").encode())
    elif op == "manifest_package":
        items = json.loads(read("items.json"))
        package = canonical({"items": items, "version": spec["parameter"]})
        write("package.json", package)
        write("manifest.json", canonical({"artifact": "package.json", "sha256": sha256(package),
                                           "count": len(items), "task_id": spec["task_id"]}))
    elif op == "sql_join_export":
        with sqlite3.connect(_confined(directory, spec["database"])) as connection:
            rows = connection.execute("SELECT c.name,SUM(o.amount) FROM customers c JOIN orders o "
                                      "ON c.id=o.customer_id GROUP BY c.id,c.name ORDER BY c.name").fetchall()
        write("revenue.csv", ("customer,revenue\n" + "".join(f"{row[0]},{row[1]}\n" for row in rows)).encode())
    else:
        raise ValueError("unregistered worker action")
    if spec["variant"] == "wrong_hash":
        target = spec["task_requirements"]["artifacts"][0]["path"]
        write(target, read(target) + b"CORRUPTED\n")
    binding = {"task_id": spec["task_id"], "session_id": spec["session_id"], "resource": spec["resource"]}
    if spec["variant"] == "wrong_binding":
        binding["task_id"] = "task:another-task"
    write("effect_binding.json", canonical(binding))
    if spec["variant"] == "ack_lost":
        # Durable effect exists; the collector exits before emitting its ACK.
        os._exit(23)
    final = snapshot(directory)
    acknowledgment = {"receipt_id": f"receipt:{spec['execution_unit_id']}:{spec['_attempt_id']}",
                       "effect_id": spec["_effect_id"], "attempt_id": spec["_attempt_id"],
                       "status": "committed", "action": spec["action"],
                       "resource": spec["resource"], "task_id": spec["task_id"],
                       "session_id": spec["session_id"], "time_ns": time.monotonic_ns(),
                       "artifact_hashes": {name: item["sha256"] for name, item in final.items()}}
    print(json.dumps(acknowledgment, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        _worker(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")), Path(sys.argv[3]).resolve())
    else:
        raise SystemExit("The controller must budget an attempt and call run_unit; direct batch execution is disabled.")
