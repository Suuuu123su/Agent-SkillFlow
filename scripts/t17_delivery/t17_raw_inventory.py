"""登记本轮全部本地记录：复用已有哈希，只首次计算未登记的文件。"""

# ruff: noqa: INP001

import argparse
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from skillflow.experiment.t17.v2.dataset_rows import HashManifest
from skillflow.experiment.t17.v2.dataset_writing import DatasetWriter
from skillflow.experiment.t17.v2.frozen import FrozenFile, file_digest, inside
from skillflow.experiment.t17.v2.unit_execution import compact_id
from skillflow.models.base import StrictModel

SCOPES = (
    "runs/t17-v2-live-20260904-01",
    "runs/t17-v2-live-20260904-02",
    "runs/t17-v2-deepseek-20260904-01",
    "runs/t17-v2-luna-defense-20260904-01",
    "runs/t17-withdrawn-model2-20260904-01",
)


class LocalRawFile(StrictModel):
    """只有相对位置和文件摘要，绝不输出私有正文。"""

    path: str
    content: FrozenFile
    basis: Literal["existing_registration", "first_registration"]
    registered_by: str | None = None


class InventorySummary(StrictModel):
    """已登记哈希仅检查存在和长度，不冒充再次逐字节复验。"""

    schema_version: Literal["t17-local-raw-inventory/1.0"] = "t17-local-raw-inventory/1.0"
    scopes: tuple[str, ...]
    file_count: int
    total_bytes: int
    reused_registrations: int
    first_registrations: int
    scope_file_counts: dict[str, int]
    tables: dict[str, tuple[str, ...]]
    excluded_directory_names: tuple[str, ...] = ("dataset", "__pycache__")
    excluded_reason: str = "公开数据集有各自完整清单；解释器缓存不是实验记录。"
    verification_scope: str = "已登记项复用原哈希并检查存在和长度；只计算缺项的字节哈希。"
    raw_contents_copied: Literal[False] = False


class _SourceUnit(BaseModel):
    """只投影索引字段；完整事实校验由标准数据集装载器负责。"""

    source_raw: str
    unit_id: str
    terminal_file: FrozenFile


class _Sources(BaseModel):
    units: tuple[_SourceUnit, ...] = ()


class _Index(BaseModel):
    files: dict[str, FrozenFile] = Field(default_factory=dict)
    source_index: _Sources | None = None
    phase_contract_sha256: str | None = None


class _Terminal(BaseModel):
    raw_files: dict[str, FrozenFile] = Field(default_factory=dict)


class _Correction(BaseModel):
    original_replay_path: str
    corrected_replay_path: str
    original_replay_file: FrozenFile
    corrected_replay_file: FrozenFile


def scoped_files(root: Path, scopes: tuple[str, ...]) -> dict[str, Path]:
    """只枚举明确的本轮目录；未关闭尝试不进入最终清单。"""
    found: dict[str, Path] = {}
    for scope in scopes:
        directory = inside(root, scope)
        if not directory.is_dir():
            raise ValueError("raw_inventory_scope_missing")
        for current, children, files in os.walk(directory):
            children[:] = sorted(n for n in children if n not in {"dataset", "__pycache__"})
            folder = Path(current)
            if folder.name.startswith("attempt-") and "stage-result.json" not in files:
                raise ValueError("raw_inventory_attempt_not_closed")
            for name in files:
                path = folder / name
                relative = path.relative_to(root).as_posix()
                found[relative] = inside(root, relative)
    return found


def register_files(
    root: Path,
    base: Path,
    entries: dict[str, FrozenFile],
    source: str,
    known: dict[str, LocalRawFile],
) -> None:
    """同一位置的多个旧登记必须相容，不能静默覆盖相冲突的证据。"""
    for name, content in entries.items():
        path = inside(base, name)
        relative = path.relative_to(root).as_posix()
        if relative in known and known[relative].content != content:
            raise ValueError("raw_inventory_registration_conflict")
        known.setdefault(
            relative,
            LocalRawFile(
                path=relative,
                content=content,
                basis="existing_registration",
                registered_by=source,
            ),
        )


def correction_bases(
    root: Path, files: dict[str, Path], known: dict[str, LocalRawFile]
) -> dict[str, Path]:
    """派生终态引用原记录，不假定正文复制到了修订目录。"""
    bases: dict[str, Path] = {}
    for source, path in sorted(files.items()):
        if path.name != "correction.json":
            continue
        correction = _Correction.model_validate_json(path.read_text(encoding="utf-8"))
        original = correction.original_replay_path
        corrected = correction.corrected_replay_path
        if original not in files or corrected not in files:
            raise ValueError("raw_inventory_correction_source_missing")
        old = _Terminal.model_validate_json(files[original].read_text(encoding="utf-8"))
        new = _Terminal.model_validate_json(files[corrected].read_text(encoding="utf-8"))
        if old.raw_files != new.raw_files:
            raise ValueError("raw_inventory_correction_source_mismatch")
        register_files(
            root,
            root,
            {
                original: correction.original_replay_file,
                corrected: correction.corrected_replay_file,
            },
            source,
            known,
        )
        bases[corrected] = files[original].parent.parent
    return bases


def stored_registrations(root: Path, files: dict[str, Path]) -> dict[str, LocalRawFile]:
    """复用阶段清单、逐任务清单和续跑来源索引，不读取私有正文。"""
    known: dict[str, LocalRawFile] = {}
    complete_roots: list[Path] = []
    for source, path in sorted(files.items()):
        if path.name not in {
            "raw-manifest.json",
            "continuation-manifest.json",
            "selected-sources.json",
        }:
            continue
        text = path.read_text(encoding="utf-8")
        if path.name != "selected-sources.json":
            index = _Index.model_validate_json(text)
            register_files(root, path.parent, index.files, source, known)
            if index.phase_contract_sha256 is not None:
                complete_roots.append(path.parent)
            sources = index.source_index
        else:
            sources = _Sources.model_validate_json(text)
        for unit in sources.units if sources is not None else ():
            terminal = (
                inside(root, unit.source_raw) / "terminals" / (compact_id(unit.unit_id) + ".json")
            )
            relative = terminal.relative_to(root).as_posix()
            if relative in files:
                register_files(root, root, {relative: unit.terminal_file}, source, known)
    bases = correction_bases(root, files, known)
    for source, path in sorted(files.items()):
        if path.parent.name != "terminals" or path.suffix != ".json":
            continue
        if any(path.is_relative_to(base) for base in complete_roots):
            continue
        terminal_index = _Terminal.model_validate_json(path.read_text(encoding="utf-8"))
        register_files(
            root, bases.get(source, path.parent.parent), terminal_index.raw_files, source, known
        )
    return known


def collect_inventory(root: Path, scopes: tuple[str, ...]) -> tuple[LocalRawFile, ...]:
    """旧登记只检查长度；首次登记前后检查文件未继续写入。"""
    root = root.resolve()
    files = scoped_files(root, scopes)
    known = stored_registrations(root, files)
    for relative, row in known.items():
        if relative not in files:
            raise ValueError("raw_inventory_registered_file_missing")
        if files[relative].stat().st_size != row.content.size_bytes:
            raise ValueError("raw_inventory_registered_size_changed")
    result = []
    for relative, path in sorted(files.items()):
        if relative in known:
            result.append(known[relative])
            continue
        before = path.stat()
        content = file_digest(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("raw_inventory_file_still_changing")
        result.append(LocalRawFile(path=relative, content=content, basis="first_registration"))
    return tuple(result)


def main() -> None:
    """只生成新清单目录，不修改任何实验目录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--scope", action="append")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    scopes = tuple(args.scope or SCOPES)
    rows = collect_inventory(root, scopes)
    writer = DatasetWriter(root, inside(root, args.output))
    writer.rows("local-raw-files.jsonl", rows, LocalRawFile)
    summary = InventorySummary(
        scopes=scopes,
        file_count=len(rows),
        total_bytes=sum(row.content.size_bytes for row in rows),
        reused_registrations=sum(row.basis == "existing_registration" for row in rows),
        first_registrations=sum(row.basis == "first_registration" for row in rows),
        scope_file_counts={
            scope: sum(row.path.startswith(scope + "/") for row in rows) for scope in scopes
        },
        tables=writer.tables,
    )
    writer.model("inventory-summary.json", summary)
    writer.schema_for(HashManifest)
    writer.model(
        "sha256-manifest.json",
        HashManifest(files={name: value.content for name, value in writer.files.items()}),
    )
    print(  # noqa: T201
        f"files={summary.file_count}; reused={summary.reused_registrations}; "
        f"first_registered={summary.first_registrations}; raw_changed=0; api_calls=0"
    )


if __name__ == "__main__":
    main()
