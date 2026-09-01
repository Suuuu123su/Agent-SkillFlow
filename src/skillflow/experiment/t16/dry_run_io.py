"""T16-B 逐条落盘和不可覆盖证据写入。"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t16.dry_run_records import DryRunTrialRecord
from skillflow.models.base import StrictModel


@dataclass(frozen=True, slots=True)
class DryRunOutputError(RuntimeError):
    """Dry Run 产物已存在或无法写入。"""

    path: Path
    detail: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return f"{self.path.name}: {self.detail}"


@dataclass(frozen=True, slots=True)
class DuplicateStoredTrialError(ValueError):
    """同一个 trial_id 不能在 JSONL 中写入两次。"""

    trial_id: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return f"重复 trial_id: {self.trial_id}"


class DryRunResultStore:
    """每条结果独立 flush 的不可覆盖 JSONL Store。"""

    def __init__(self, path: Path) -> None:
        """保存目标路径和进程内去重集合。"""
        self.path = path
        self._seen: set[str] = set()

    def initialize(self) -> None:
        """独占创建空结果文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8", newline="\n"):
                pass
        except OSError as error:
            raise DryRunOutputError(self.path, str(error)) from error

    def append(self, record: DryRunTrialRecord) -> None:
        """Schema 已验证后追加一条，并在返回前关闭文件完成 flush。"""
        trial_id = record.result.trial_id
        if trial_id in self._seen:
            raise DuplicateStoredTrialError(trial_id)
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(record.model_dump_json())
                stream.write("\n")
        except OSError as error:
            raise DryRunOutputError(self.path, str(error)) from error
        self._seen.add(trial_id)


def read_trial_records(path: Path) -> tuple[DryRunTrialRecord, ...]:
    """逐行复验已保存 Trial Record。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise DryRunOutputError(path, str(error)) from error
    return tuple(DryRunTrialRecord.model_validate_json(line) for line in lines)


def write_json_model(path: Path, model: StrictModel) -> None:
    """确定性、不可覆盖写入一个证据模型。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(model.model_dump_json(indent=2))
            stream.write("\n")
    except OSError as error:
        raise DryRunOutputError(path, str(error)) from error


def sha256_path(path: Path) -> str:
    """返回已落盘证据的 SHA-256。"""
    try:
        content = path.read_bytes()
    except OSError as error:
        raise DryRunOutputError(path, str(error)) from error
    return hashlib.sha256(content).hexdigest()
