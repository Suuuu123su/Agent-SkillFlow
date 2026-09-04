"""数据集文件集、字节哈希、静态格式和逻辑记录数核对。"""

import json
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

from skillflow.experiment.t17.v2.dataset_models import DatasetManifest
from skillflow.experiment.t17.v2.dataset_rows import HashManifest
from skillflow.experiment.t17.v2.dataset_tables import csv_table_rows
from skillflow.experiment.t17.v2.dataset_writing import guard_public
from skillflow.experiment.t17.v2.frozen import inside, verify_files
from skillflow.experiment.t17.v2.loading import read_model


def verify_dataset_files(directory: Path) -> DatasetManifest:
    """先核对字节和文件集合，不能静默忽略额外表或丢失的行。"""
    root = directory.resolve()
    hashes = read_model(root / "sha256-manifest.json", HashManifest)
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(hashes.files) | {"sha256-manifest.json"}:
        raise ValueError("v2_dataset_file_set_drift")
    verify_files(root, hashes.files)
    manifest = read_model(root / "dataset-manifest.json", DatasetManifest)
    _validate_tables(manifest)
    if set(manifest.files) | {"dataset-manifest.json"} != set(hashes.files):
        raise ValueError("v2_dataset_manifest_file_set")
    for name, item in manifest.files.items():
        if item.content != hashes.files[name]:
            raise ValueError("v2_dataset_manifest_hash_mismatch")
        schema = json.loads(inside(root, item.schema_path).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        count = _validate_file(inside(root, name), item.format, validator)
        if count != item.record_count:
            raise ValueError("v2_dataset_record_count_mismatch")
    return manifest


def _validate_tables(manifest: DatasetManifest) -> None:
    expected = {
        "core-trials.jsonl",
        "replay-pairs.jsonl",
        "task-success-evidence.jsonl",
        "effect-receipts.jsonl",
        "provenance-edges.jsonl",
        "api-usage.jsonl",
        "metrics-long.csv",
        "condition-summary.csv",
        "skill-comparison-ready.csv",
        "model-comparison.csv",
        "defense-comparison.csv",
        "skill-comparison.csv",
    }
    if set(manifest.tables) != expected:
        raise ValueError("v2_dataset_logical_table_set")
    all_parts: list[str] = []
    for name, parts in manifest.tables.items():
        path = PurePosixPath(name)
        ordered = (
            name,
            *(
                str(path.with_name(f"{path.stem}.part-{i:04d}{path.suffix}"))
                for i in range(2, len(parts) + 1)
            ),
        )
        if not parts or parts != ordered:
            raise ValueError("v2_dataset_table_parts_order")
        all_parts.extend(parts)
    table_files = {name for name, item in manifest.files.items() if item.format in {"jsonl", "csv"}}
    if len(set(all_parts)) != len(all_parts) or set(all_parts) != table_files:
        raise ValueError("v2_dataset_table_parts_binding")


def _validate_file(path: Path, format_name: str, validator: Draft202012Validator) -> int:
    if format_name == "jsonl":
        count = 0
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                guard_public(line)
                validator.validate(json.loads(line))
                count += 1
        return count
    text = path.read_text(encoding="utf-8")
    guard_public(text)
    if format_name == "json":
        validator.validate(json.loads(text))
        return 1
    if format_name == "csv":
        return sum(1 for _ in csv_table_rows(path.parent, (path.name,)))
    validator.validate(text)
    return len(text.splitlines())
