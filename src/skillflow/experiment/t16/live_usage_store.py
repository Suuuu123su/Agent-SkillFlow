"""T16-D.2R 逐响应实际用量与 Trial 终态的追加式存储。"""

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, unique
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.live_record_builders import add_usage
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


@unique
class ActualUsageStatus(StrEnum):
    """一条 Trial 的实际用量覆盖程度。"""

    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_AVAILABLE = "not_available"


@unique
class LiveTrialTerminalStatus(StrEnum):
    """v3.1 Trial 的持久化终态。"""

    COMPLETED = "completed"
    STEP_LIMIT_EXHAUSTED = "step_limit_exhausted"
    PARTIAL = "partial"


class LiveUsageJournalEvent(StrictModel):
    """不含 Prompt/响应正文的累计实际用量事件。"""

    schema_version: Literal["0.1"] = "0.1"
    sequence: PositiveInt
    event_type: Literal["response", "terminal"]
    protocol_id: NonEmptyStr
    config_id: NonEmptyStr
    config_sha256: Sha256Hex
    trial_id: NonEmptyStr
    api_call_count: NonNegativeInt
    response_count: NonNegativeInt
    total_reserved_usd: NonNegativeMoney
    run_reserved_usd: NonNegativeMoney
    actual_usage_status: ActualUsageStatus
    observed_token_usage: TokenUsage | None
    observed_estimated_cost_usd: NonNegativeMoney | None
    terminal_status: LiveTrialTerminalStatus | None = None
    stop_detail: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_explicit_usage_coverage(self) -> Self:
        """未知实际用量必须为 null，不能伪装成零。"""
        if self.response_count > self.api_call_count:
            self._invalid("response_count 不能大于 api_call_count")
        expected = _usage_status(self.api_call_count, self.response_count)
        if self.actual_usage_status is not expected:
            self._invalid("actual_usage_status 与调用/响应计数不一致")
        if self.response_count == 0:
            if self.observed_token_usage is not None:
                self._invalid("无实际响应时 Token 用量必须为 N/A")
            if self.observed_estimated_cost_usd is not None:
                self._invalid("无实际响应时费用必须为 N/A")
        elif self.observed_token_usage is None or self.observed_estimated_cost_usd is None:
            self._invalid("有实际响应时必须保存已观察用量与费用")
        if self.event_type == "response":
            if self.terminal_status is not None or self.stop_detail is not None:
                self._invalid("响应事件不得伪装成 Trial 终态")
        elif self.terminal_status is None:
            self._invalid("终态事件必须声明 terminal_status")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16d2r_usage_event_invalid", detail)


@dataclass(frozen=True, slots=True)
class LiveUsageStoreError(RuntimeError):
    """用量日志无法安全创建、追加或解析。"""

    detail: str

    def __str__(self) -> str:
        """返回不含 Prompt、响应或凭据的稳定诊断。"""
        return self.detail


@dataclass(frozen=True, slots=True)
class _UsageSnapshot:
    """由 Trial tracker 提交给 Journal 的累计内存快照。"""

    event_type: Literal["response", "terminal"]
    trial_id: str
    api_call_count: int
    response_count: int
    total_reserved_usd: Decimal
    run_reserved_usd: Decimal
    observed_token_usage: TokenUsage | None
    observed_estimated_cost_usd: Decimal | None
    terminal_status: LiveTrialTerminalStatus | None = None
    stop_detail: str | None = None


class LiveUsageJournal:
    """逐条 fsync 保存实际响应；与调用前 Budget Journal 并行存在。"""

    def __init__(
        self,
        path: Path,
        config: T16CLiveConfig,
        *,
        protocol_id: str,
    ) -> None:
        """绑定新协议和执行配置；不接收或保存任何凭据。"""
        self.path = path
        self._config = config
        self._protocol_id = protocol_id
        self._config_sha256 = _canonical_sha256(config.model_dump(mode="json"))
        self._events: list[LiveUsageJournalEvent] = []
        self._terminal_trials: set[str] = set()
        self._opened = False

    @property
    def config_sha256(self) -> str:
        """返回新执行配置的稳定 SHA-256。"""
        return self._config_sha256

    def open_new(self) -> None:
        """独占新建日志，绝不覆盖已有 Attempt。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            detail = f"无法新建用量日志: {self.path}"
            raise LiveUsageStoreError(detail) from error
        self._opened = True

    def start_trial(self, trial_id: str) -> "LiveTrialUsageTracker":
        """创建一条 Trial 私有的内存累计器。"""
        if not self._opened:
            raise LiveUsageStoreError("用量日志尚未打开")
        if trial_id in self._terminal_trials:
            detail = f"Trial 已存在终态: {trial_id}"
            raise LiveUsageStoreError(detail)
        return LiveTrialUsageTracker(self, trial_id)

    def append_snapshot(self, snapshot: _UsageSnapshot) -> LiveUsageJournalEvent:
        """追加一个已验证的累计快照并在返回前同步磁盘。"""
        if not self._opened:
            raise LiveUsageStoreError("用量日志尚未打开")
        if snapshot.trial_id in self._terminal_trials:
            detail = f"Trial 已存在终态: {snapshot.trial_id}"
            raise LiveUsageStoreError(detail)
        event = LiveUsageJournalEvent(
            sequence=len(self._events) + 1,
            event_type=snapshot.event_type,
            protocol_id=self._protocol_id,
            config_id=self._config.id,
            config_sha256=self._config_sha256,
            trial_id=snapshot.trial_id,
            api_call_count=snapshot.api_call_count,
            response_count=snapshot.response_count,
            total_reserved_usd=snapshot.total_reserved_usd,
            run_reserved_usd=snapshot.run_reserved_usd,
            actual_usage_status=_usage_status(
                snapshot.api_call_count,
                snapshot.response_count,
            ),
            observed_token_usage=snapshot.observed_token_usage,
            observed_estimated_cost_usd=snapshot.observed_estimated_cost_usd,
            terminal_status=snapshot.terminal_status,
            stop_detail=snapshot.stop_detail,
        )
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(event.model_dump_json())
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise LiveUsageStoreError("用量日志追加失败") from error
        self._events.append(event)
        if snapshot.event_type == "terminal":
            self._terminal_trials.add(snapshot.trial_id)
        return event


@dataclass(slots=True)
class LiveTrialUsageTracker:
    """一条 Trial 的调用、响应、Token 与费用累计状态。"""

    journal: LiveUsageJournal
    trial_id: str
    api_call_count: int = 0
    response_count: int = 0
    total_reserved_usd: Decimal = Decimal(0)
    run_reserved_usd: Decimal = Decimal(0)
    observed_token_usage: TokenUsage | None = None
    observed_estimated_cost_usd: Decimal | None = None
    _finalized: bool = False

    def record_attempt(self, budget: BudgetLedger) -> None:
        """在 Client 调用前累计尝试数；保守预留仍由 Budget Journal 先写盘。"""
        self._require_active()
        self.api_call_count += 1
        self.total_reserved_usd = budget.total_spent_usd
        self.run_reserved_usd = budget.run_spent_usd

    def record_response(self, usage: TokenUsage, estimated_cost_usd: Decimal) -> None:
        """API 响应一返回就累计并 fsync，不等待 Session 或 Trial 完成。"""
        self._require_active()
        self.response_count += 1
        self.observed_token_usage = (
            usage
            if self.observed_token_usage is None
            else add_usage(self.observed_token_usage, usage)
        )
        self.observed_estimated_cost_usd = (
            estimated_cost_usd
            if self.observed_estimated_cost_usd is None
            else self.observed_estimated_cost_usd + estimated_cost_usd
        )
        self.journal.append_snapshot(
            _UsageSnapshot(
                event_type="response",
                trial_id=self.trial_id,
                api_call_count=self.api_call_count,
                response_count=self.response_count,
                total_reserved_usd=self.total_reserved_usd,
                run_reserved_usd=self.run_reserved_usd,
                observed_token_usage=self.observed_token_usage,
                observed_estimated_cost_usd=self.observed_estimated_cost_usd,
            )
        )

    def finalize(self, status: LiveTrialTerminalStatus, stop_detail: str | None = None) -> None:
        """在 Runner finally 中保存完整、Step 耗尽或其他 partial 终态。"""
        self._require_active()
        self.journal.append_snapshot(
            _UsageSnapshot(
                event_type="terminal",
                trial_id=self.trial_id,
                api_call_count=self.api_call_count,
                response_count=self.response_count,
                total_reserved_usd=self.total_reserved_usd,
                run_reserved_usd=self.run_reserved_usd,
                observed_token_usage=self.observed_token_usage,
                observed_estimated_cost_usd=self.observed_estimated_cost_usd,
                terminal_status=status,
                stop_detail=stop_detail,
            )
        )
        self._finalized = True

    def _require_active(self) -> None:
        if self._finalized:
            detail = f"Trial 用量已终结: {self.trial_id}"
            raise LiveUsageStoreError(detail)


def load_live_usage_events(path: Path) -> tuple[LiveUsageJournalEvent, ...]:
    """严格读取用量日志，并验证全局 sequence 连续。"""
    try:
        lines = tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)
    except OSError as error:
        detail = f"无法读取用量日志: {path}"
        raise LiveUsageStoreError(detail) from error
    events = tuple(LiveUsageJournalEvent.model_validate_json(line) for line in lines)
    if tuple(item.sequence for item in events) != tuple(range(1, len(events) + 1)):
        detail = "用量日志 sequence 不连续"
        raise LiveUsageStoreError(detail)
    return events


def _usage_status(api_call_count: int, response_count: int) -> ActualUsageStatus:
    if response_count == 0:
        return ActualUsageStatus.NOT_AVAILABLE
    if response_count < api_call_count:
        return ActualUsageStatus.PARTIAL
    return ActualUsageStatus.COMPLETE


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
