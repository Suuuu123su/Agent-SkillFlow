"""Canonical storage and append-only research receipts (standard library only)."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE = Path(__file__).resolve().parent
CHANNELS = ('receipt', 'grant', 'provenance', 'counterfactual',
            'task_success_evidence', 'lifecycle', 'scope_lifetime',
            'decision_reason', 'failure')
SEEDS = (19119, 19120, 19121)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def append_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('ab') as handle:
        handle.write(canonical(value) + b'\n')
        handle.flush()


def read_rows(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
            if line] if path.exists() else []


def write_csv(path, rows):
    rows = list(rows)
    with Path(path).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def git_sha():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                   text=True).strip()


def code_hashes():
    return {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p.read_bytes())
            for p in sorted(CODE.iterdir()) if p.suffix in ('.py', '.json')}


def verify_hashes(mapping):
    for rel, expected in mapping.items():
        if sha((ROOT / rel).read_bytes()) != expected:
            raise ValueError('Frozen input changed: ' + rel)


def frozen_json(path, value):
    write_json(path, value, exclusive=True)
    Path(str(path) + '.sha256').write_text(sha(Path(path).read_bytes()) + '\n', encoding='ascii')


def load_frozen(path):
    data = Path(path).read_bytes()
    if sha(data) != Path(str(path) + '.sha256').read_text(encoding='ascii').strip():
        raise ValueError('Frozen JSON digest mismatch')
    return json.loads(data)
