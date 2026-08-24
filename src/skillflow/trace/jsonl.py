"""不覆盖已有输出的规范 JSONL 写入器。"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from skillflow.models.base import StrictModel


@dataclass(frozen=True, slots=True)
class TraceWriteError(Exception):
    """Trace 文件无法安全创建。"""

    path: Path
    reason: str

    def __str__(self) -> str:
        """返回目标路径和底层原因。"""
        return f"Trace 写入失败：{self.path}：{self.reason}"


def write_jsonl(path: Path, records: Sequence[StrictModel]) -> None:
    """以创建模式写入无明文内容的规范 JSONL。"""
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            for record in records:
                line = json.dumps(
                    record.model_dump(mode="json"),
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                stream.write(f"{line}\n")
    except OSError as error:
        reason = error.strerror if error.strerror is not None else error.__class__.__name__
        raise TraceWriteError(path, reason) from error
