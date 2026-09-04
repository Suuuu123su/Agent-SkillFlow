"""项目内路径和不可变字节清单，不读取或保存凭据。"""

import hashlib
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.models.base import NonEmptyStr, StrictModel


class FrozenFile(StrictModel):
    """单个已存在文件的哈希、长度及可选逐行记录数。"""

    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]
    records: Annotated[int, Field(ge=0)] | None = None


class BaselineSnapshot(StrictModel):
    """新版首次修改实验实现前登记的历史不可变文件集合。"""

    schema_version: Literal["2.0"] = "2.0"
    baseline_commit: NonEmptyStr
    created_at: datetime
    historical_files: dict[NonEmptyStr, FrozenFile]
    minimal_status: Literal["completed"] = "completed"
    full_t17_status: Literal["in_progress"] = "in_progress"
    independent_review: Literal["REVIEW_UNAVAILABLE"] = "REVIEW_UNAVAILABLE"
    new_paid_api_calls: Literal[0] = 0


def relative_path(value: str) -> str:
    """只允许规范项目相对路径，拒绝盘符、反斜线和上级跳转。"""
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or ":" in value
        or any(part in {"..", "."} for part in value.split("/"))
        or path.as_posix() != value
    ):
        raise ValueError("v2_relative_path_required")
    return value


def inside(root: Path, value: str) -> Path:
    """解析后再次验证，拒绝符号链接越过项目边界。"""
    path = (root / relative_path(value)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("v2_relative_path_escape")
    return path


def file_digest(path: Path) -> FrozenFile:
    """只读流式散列；记录数不包含空行。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    count = None
    if path.suffix == ".jsonl":
        with path.open("rb") as handle:
            count = sum(bool(line.strip()) for line in handle)
    return FrozenFile(sha256=digest.hexdigest(), size_bytes=path.stat().st_size, records=count)


def digest_files(root: Path, paths: Iterable[str]) -> dict[str, FrozenFile]:
    """同一项目内机械登记，不改写输入。"""
    return {value: file_digest(inside(root, value)) for value in sorted(set(paths))}


def verify_files(root: Path, expected: Mapping[str, FrozenFile]) -> None:
    """缺文件和字节漂移均拒绝；不恢复、覆盖或删除原文件。"""
    for value, digest in expected.items():
        path = inside(root, value)
        if not path.is_file() or file_digest(path) != digest:
            raise ValueError("v2_frozen_file_drift:" + value)


def historical_paths(root: Path) -> tuple[str, ...]:
    """列出全部旧 T16/T17 原始记录、配置、总结和公开证据。"""
    paths: set[Path] = set()
    for parent in (root / "experiments" / "t16", root / "experiments" / "t17"):
        paths.update(
            path
            for path in parent.rglob("*")
            if path.is_file() and not path.is_relative_to(root / "experiments" / "t17" / "v2")
        )
    for parent in (root / "runs").iterdir():
        if (
            parent.is_dir()
            and parent.name.startswith(("t16", "t17"))
            and not parent.name.startswith("t17-v2-")
        ):
            paths.update(path for path in parent.rglob("*") if path.is_file())
    for directory in ("docs/summaries", "docs/evidence"):
        paths.update(
            path
            for path in (root / directory).iterdir()
            if path.is_file()
            and path.name.lower().startswith(("t16", "t17"))
            and not path.name.lower().startswith("t17-v2-")
            and "_v2_summary" not in path.name.lower()
            and path.name != "T17_Complete_Summary_V2.md"
        )
    paths.update(root / value for value in ("EXPERIMENT_AUDIT.md", "EXPERIMENT_AUDIT.json"))
    paths.update(path for path in (root / "scenarios").rglob("*") if path.is_file())
    return tuple(sorted(path.relative_to(root).as_posix() for path in paths))
