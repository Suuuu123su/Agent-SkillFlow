"""隔离 Workspace 的不可变 checkpoint。"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from skillflow.instrumentation.errors import WorkspaceEscapeError, WorkspaceResourceError


@dataclass(frozen=True, slots=True)
class WorkspaceFileSnapshot:
    """一个 Workspace 文件的相对路径、摘要与私有内容。"""

    relative_path: str
    content_hash: str
    content_length: int
    content: bytes


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """Workspace 中全部普通文件的有序快照。"""

    files: tuple[WorkspaceFileSnapshot, ...]


def capture_workspace(root: Path) -> WorkspaceSnapshot:
    """只读取根内普通文件，拒绝符号链接与路径逃逸。"""
    resolved_root = root.resolve()
    snapshots: list[WorkspaceFileSnapshot] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise WorkspaceResourceError(str(path), "checkpoint 不接受符号链接")
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(resolved_root):
            raise WorkspaceEscapeError(str(path))
        content = path.read_bytes()
        snapshots.append(
            WorkspaceFileSnapshot(
                relative_path=resolved.relative_to(resolved_root).as_posix(),
                content_hash=hashlib.sha256(content).hexdigest(),
                content_length=len(content),
                content=content,
            )
        )
    return WorkspaceSnapshot(tuple(snapshots))


def restore_workspace(snapshot: WorkspaceSnapshot, root: Path) -> None:
    """把快照写入已存在且为空的全新 Workspace。"""
    if any(root.iterdir()):
        raise WorkspaceResourceError(str(root), "restore 目标 Workspace 必须为空")
    resolved_root = root.resolve()
    for item in snapshot.files:
        target = (root / item.relative_path).resolve()
        if not target.is_relative_to(resolved_root):
            raise WorkspaceEscapeError(item.relative_path)
        valid = (
            len(item.content) == item.content_length
            and hashlib.sha256(item.content).hexdigest() == item.content_hash
        )
        if not valid:
            raise WorkspaceResourceError(item.relative_path, "checkpoint 内容摘要不一致")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(item.content)
