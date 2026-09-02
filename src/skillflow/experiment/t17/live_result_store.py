"""T17 Live 核心与 Replay Raw 索引的不可覆盖 JSONL 存储。"""

import os
from enum import StrEnum, unique
from pathlib import Path

from skillflow.experiment.t17.live_attempt_models import T17LiveUnitRecord


@unique
class T17LiveResultStoreErrorCode(StrEnum):
    """Raw 索引的封闭存储错误。"""

    OPEN_FAILED = "open_failed"
    NOT_OPEN = "not_open"
    SEQUENCE_INVALID = "sequence_invalid"
    UNIT_DUPLICATE = "unit_duplicate"
    APPEND_FAILED = "append_failed"
    READ_FAILED = "read_failed"


class T17LiveResultStoreError(RuntimeError):
    """Raw 索引无法独占创建、追加或严格读取。"""

    __slots__ = ("code", "identifier")

    def __init__(
        self,
        code: T17LiveResultStoreErrorCode,
        identifier: str | None = None,
    ) -> None:
        """保存封闭存储码并保留 Exception 运行时状态。"""
        super().__init__(code.value, identifier)
        self.code = code
        self.identifier = identifier

    def __str__(self) -> str:
        """返回不含正文和秘密的稳定诊断。"""
        suffix = "" if self.identifier is None else f":{self.identifier}"
        return f"{self.code.value}{suffix}"


class T17LiveResultStore:
    """只接受连续 sequence 和唯一 unit_id 的追加式 Raw 索引。"""

    def __init__(self, path: Path) -> None:
        """绑定一个尚不存在的 JSONL 路径。"""
        self.path = path
        self._records: list[T17LiveUnitRecord] = []
        self._unit_ids: set[str] = set()
        self._opened = False

    @property
    def next_sequence(self) -> int:
        """返回下一条合法 sequence。"""
        return len(self._records) + 1

    @property
    def records(self) -> tuple[T17LiveUnitRecord, ...]:
        """返回当前进程已持久化的不可变记录。"""
        return tuple(self._records)

    def open_new(self) -> None:
        """独占新建结果文件，绝不覆盖旧 Attempt。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise T17LiveResultStoreError(
                T17LiveResultStoreErrorCode.OPEN_FAILED,
                self.path.name,
            ) from error
        self._opened = True

    def append(self, record: T17LiveUnitRecord) -> None:
        """验证身份和顺序后追加并在返回前 fsync。"""
        if not self._opened:
            raise T17LiveResultStoreError(T17LiveResultStoreErrorCode.NOT_OPEN)
        if record.sequence != self.next_sequence:
            raise T17LiveResultStoreError(T17LiveResultStoreErrorCode.SEQUENCE_INVALID)
        if record.unit_id in self._unit_ids:
            raise T17LiveResultStoreError(
                T17LiveResultStoreErrorCode.UNIT_DUPLICATE,
                record.unit_id,
            )
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(record.model_dump_json())
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise T17LiveResultStoreError(T17LiveResultStoreErrorCode.APPEND_FAILED) from error
        self._records.append(record)
        self._unit_ids.add(record.unit_id)


def load_live_unit_records(path: Path) -> tuple[T17LiveUnitRecord, ...]:
    """严格读取 Raw JSONL，并验证 sequence 与 unit_id 唯一性。"""
    try:
        lines = tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)
    except OSError as error:
        raise T17LiveResultStoreError(
            T17LiveResultStoreErrorCode.READ_FAILED,
            path.name,
        ) from error
    records = tuple(T17LiveUnitRecord.model_validate_json(line) for line in lines)
    if tuple(item.sequence for item in records) != tuple(range(1, len(records) + 1)):
        raise T17LiveResultStoreError(T17LiveResultStoreErrorCode.SEQUENCE_INVALID)
    identifiers = tuple(item.unit_id for item in records)
    if len(set(identifiers)) != len(identifiers):
        raise T17LiveResultStoreError(T17LiveResultStoreErrorCode.UNIT_DUPLICATE)
    return records
