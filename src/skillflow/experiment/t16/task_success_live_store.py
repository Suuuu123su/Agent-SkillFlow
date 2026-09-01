"""T16-D.2 逐条 fsync 的原始记录与不可变 JSON 产物存储。"""

import os
from pathlib import Path

from pydantic import BaseModel

from skillflow.experiment.t16.task_success_live_models import T16D2RawTrialRecord


class T16D2StoreError(RuntimeError):
    """新 Attempt 的不可覆盖存储边界失败。"""


class T16D2RawStore:
    """单 JSONL 原子保存平台快照和 LiveTrialRecord。"""

    def __init__(self, path: Path) -> None:
        """保存新 Attempt 的唯一 Raw JSONL 路径。"""
        self.path = path
        self._trial_ids: set[str] = set()
        self._opened = False

    def open_new(self) -> None:
        """只允许新建，绝不覆盖已有 Attempt。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _write_exclusive(self.path, "", trailing_newline=False)
        self._opened = True

    def append(self, record: T16D2RawTrialRecord) -> None:
        """追加一条完整原子记录并同步磁盘。"""
        if not self._opened:
            detail = "Raw Store 尚未打开"
            raise T16D2StoreError(detail)
        trial_id = record.live_trial.result.trial_id
        if trial_id in self._trial_ids:
            detail = f"重复 Trial ID: {trial_id}"
            raise T16D2StoreError(detail)
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(record.model_dump_json())
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            detail = f"Raw Store 追加失败: {self.path.name}"
            raise T16D2StoreError(detail) from error
        self._trial_ids.add(trial_id)

    def read(self) -> tuple[T16D2RawTrialRecord, ...]:
        """严格解析当前所有已落盘记录。"""
        return load_t16d2_raw_records(self.path)


def load_t16d2_raw_records(path: Path) -> tuple[T16D2RawTrialRecord, ...]:
    """从不可变 JSONL 读取 D.2 原始记录。"""
    try:
        lines = tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)
    except OSError as error:
        detail = f"无法读取 Raw Store: {path.name}"
        raise T16D2StoreError(detail) from error
    records = tuple(T16D2RawTrialRecord.model_validate_json(line) for line in lines)
    trial_ids = tuple(item.live_trial.result.trial_id for item in records)
    if len(set(trial_ids)) != len(trial_ids):
        detail = "Raw Store 包含重复 Trial ID"
        raise T16D2StoreError(detail)
    return records


def write_immutable_json(path: Path, model: BaseModel | str) -> None:
    """以 Pydantic JSON 或字符串形式独占写入单个产物。"""
    content = model if isinstance(model, str) else model.model_dump_json(indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_exclusive(path, content, trailing_newline=True)


def _write_exclusive(path: Path, content: str, *, trailing_newline: bool) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            if trailing_newline:
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        detail = f"不可变文件已存在或无法写入: {path}"
        raise T16D2StoreError(detail) from error
