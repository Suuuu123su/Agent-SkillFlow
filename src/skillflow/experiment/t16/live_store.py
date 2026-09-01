"""T16-C Trial 与保守预算的追加式断点存储。"""

import hashlib
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t16.budget import BudgetConfig, BudgetLedger
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


@dataclass(frozen=True, slots=True)
class LiveStoreError(RuntimeError):
    """追加式证据文件不能安全打开或解析。"""

    path: Path
    detail: str

    def __str__(self) -> str:
        """返回稳定文件诊断。"""
        return f"{self.path.name}: {self.detail}"


@dataclass(frozen=True, slots=True)
class DuplicateLiveTrialError(ValueError):
    """同一个真实模型 Trial 不允许重复写入。"""

    trial_id: str

    def __str__(self) -> str:
        """返回稳定 Trial 诊断。"""
        return f"重复 live trial_id: {self.trial_id}"


class BudgetSnapshot(StrictModel):
    """每次 API 调用前已占用的保守预算快照。"""

    schema_version: Literal["0.1"] = "0.1"
    sequence: NonNegativeInt
    budget_config_sha256: NonEmptyStr
    total_reserved_usd: NonNegativeMoney
    run_reserved_usd: NonNegativeMoney
    agent_turns: NonNegativeInt
    retries: NonNegativeInt


class LivePhaseContractSnapshot(StrictModel):
    """一次付费阶段恢复所绑定的不可变合同指纹。"""

    schema_version: Literal["0.1"] = "0.1"
    phase: NonEmptyStr
    phase_contract_sha256: Sha256Hex


class LivePhaseContractStore:
    """在任何 Provider 调用前创建或复核阶段合同。"""

    def __init__(self, path: Path) -> None:
        """保存阶段合同路径；显式 open 前不触碰文件。"""
        self.path = path

    def open(self, *, resume: bool, phase: str, phase_contract_sha256: str) -> None:
        """新阶段独占写入合同；恢复阶段要求文件与当前合同精确一致。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        expected = LivePhaseContractSnapshot(
            phase=phase,
            phase_contract_sha256=phase_contract_sha256,
        )
        if not resume:
            _exclusive_write(self.path, expected.model_dump_json())
            return
        lines = _read_lines(self.path)
        if len(lines) != 1:
            raise LiveStoreError(self.path, "phase contract 必须精确包含一条记录")
        stored = LivePhaseContractSnapshot.model_validate_json(lines[0])
        if stored.phase != phase:
            raise LiveStoreError(self.path, "phase 与当前恢复请求不一致")
        if stored.phase_contract_sha256 != phase_contract_sha256:
            raise LiveStoreError(self.path, "phase_contract_sha256 与当前执行合同不一致")


class LiveResultStore:
    """逐条 fsync、可严格恢复且拒绝重复的 JSONL Store。"""

    def __init__(self, path: Path) -> None:
        """保存路径；在显式 open 前不触碰文件。"""
        self.path = path
        self._seen: set[str] = set()
        self._opened = False

    @property
    def completed_trial_ids(self) -> set[str]:
        """返回副本，避免调用方改写 Store 内部状态。"""
        return set(self._seen)

    def open(self, *, resume: bool) -> None:
        """新建不可覆盖文件，或复验并恢复已有文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if resume:
            records = self.read_records()
            self._seen = {item.result.trial_id for item in records}
            if len(self._seen) != len(records):
                raise LiveStoreError(self.path, "已有结果包含重复 trial_id")
        else:
            _exclusive_create(self.path)
        self._opened = True

    def append(self, record: LiveTrialRecord) -> None:
        """追加一条完整 Trial 并在返回前同步到磁盘。"""
        self._require_open()
        trial_id = record.result.trial_id
        if trial_id in self._seen:
            raise DuplicateLiveTrialError(trial_id)
        _append_line(self.path, record.model_dump_json())
        self._seen.add(trial_id)

    def read_records(self) -> tuple[LiveTrialRecord, ...]:
        """逐行严格解析已有记录；任何损坏都拒绝恢复。"""
        lines = _read_lines(self.path)
        return tuple(LiveTrialRecord.model_validate_json(line) for line in lines)

    def _require_open(self) -> None:
        if not self._opened:
            raise LiveStoreError(self.path, "Store 尚未打开")


class LiveBudgetJournal:
    """调用前追加预算占用，崩溃后不释放不确定调用。"""

    def __init__(self, path: Path, config: BudgetConfig) -> None:
        """绑定预算配置；日志不包含 Provider 凭据。"""
        self.path = path
        self._config = config
        self._config_sha256 = hashlib.sha256(config.model_dump_json().encode()).hexdigest()
        self._snapshots: list[BudgetSnapshot] = []
        self._opened = False

    def open(self, *, resume: bool) -> None:
        """新建日志，或复验配置指纹后恢复全部占用。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if resume:
            self._snapshots = [
                BudgetSnapshot.model_validate_json(line) for line in _read_lines(self.path)
            ]
            if any(item.budget_config_sha256 != self._config_sha256 for item in self._snapshots):
                raise LiveStoreError(self.path, "预算配置指纹与已有日志不一致")
        else:
            _exclusive_create(self.path)
        self._opened = True

    def record(self, budget: BudgetLedger) -> None:
        """在真实 Client 调用前持久化新的保守预算状态。"""
        self._require_open()
        if budget.config != self._config:
            raise LiveStoreError(self.path, "BudgetLedger 配置不一致")
        snapshot = BudgetSnapshot(
            sequence=len(self._snapshots) + 1,
            budget_config_sha256=self._config_sha256,
            total_reserved_usd=budget.total_spent_usd,
            run_reserved_usd=budget.run_spent_usd,
            agent_turns=budget.agent_turns,
            retries=budget.retries,
        )
        _append_line(self.path, snapshot.model_dump_json())
        self._snapshots.append(snapshot)

    def latest_budget(self) -> BudgetLedger:
        """返回最后一次调用前占用；空日志返回零账本。"""
        if not self._snapshots:
            return BudgetLedger(self._config)
        latest = self._snapshots[-1]
        return BudgetLedger(
            config=self._config,
            total_spent_usd=latest.total_reserved_usd,
            run_spent_usd=latest.run_reserved_usd,
            agent_turns=latest.agent_turns,
            retries=latest.retries,
        )

    def _require_open(self) -> None:
        if not self._opened:
            raise LiveStoreError(self.path, "Budget Journal 尚未打开")


def _exclusive_create(path: Path) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise LiveStoreError(path, str(error)) from error


def _exclusive_write(path: Path, content: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise LiveStoreError(path, str(error)) from error


def _append_line(path: Path, content: str) -> None:
    try:
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise LiveStoreError(path, str(error)) from error


def _read_lines(path: Path) -> tuple[str, ...]:
    try:
        return tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)
    except OSError as error:
        raise LiveStoreError(path, str(error)) from error
