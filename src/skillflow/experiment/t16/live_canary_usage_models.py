"""T16-D.2 v3.1 Canary 的逐响应与 Partial Trial 用量模型。"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Literal, Protocol, Self, assert_never

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.live_usage_store import (
    ActualUsageStatus,
    LiveTrialTerminalStatus,
)
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CanaryUsageJournalEvent(StrictModel):
    """一次响应或 Trial 终态的即时、脱敏、追加式证据。"""

    schema_version: Literal["0.2"] = "0.2"
    sequence: PositiveInt
    recorded_at: AwareDatetime
    event_type: Literal["response", "terminal"]
    protocol_id: NonEmptyStr
    config_id: NonEmptyStr
    config_sha256: Sha256Hex
    trial_id: NonEmptyStr
    condition_id: NonEmptyStr
    session_index: NonNegativeInt | None
    agent_step: PositiveInt | None
    provider: NonEmptyStr
    model_id: NonEmptyStr
    model_revision: NonEmptyStr | None
    api_call_count: NonNegativeInt
    response_count: NonNegativeInt
    total_reserved_usd: NonNegativeMoney
    run_reserved_usd: NonNegativeMoney
    response_token_usage: TokenUsage | None
    response_estimated_cost_usd: NonNegativeMoney | None
    actual_usage_status: ActualUsageStatus
    observed_token_usage: TokenUsage | None
    observed_estimated_cost_usd: NonNegativeMoney | None
    completed_session_indices: tuple[NonNegativeInt, ...] = ()
    terminal_status: LiveTrialTerminalStatus | None = None
    stop_detail: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_unambiguous_response_or_terminal(self) -> Self:
        """拒绝把缺失用量写成 0，或把终态伪装成响应。"""
        if self.response_count > self.api_call_count:
            self._invalid("response_count 不能大于 api_call_count")
        if self.actual_usage_status is not usage_status(
            self.api_call_count,
            self.response_count,
        ):
            self._invalid("actual_usage_status 与调用/响应计数不一致")
        if self.response_count == 0:
            if self.observed_token_usage is not None:
                self._invalid("无响应时累计 Token 必须为 N/A")
            if self.observed_estimated_cost_usd is not None:
                self._invalid("无响应时累计费用必须为 N/A")
        elif self.observed_token_usage is None or self.observed_estimated_cost_usd is None:
            self._invalid("有响应时必须保存累计 Token 与费用")
        if tuple(sorted(set(self.completed_session_indices))) != self.completed_session_indices:
            self._invalid("completed_session_indices 必须唯一且递增")
        match self.event_type:
            case "response":
                self._require_response_fields()
            case "terminal":
                self._require_terminal_fields()
            case unreachable:
                assert_never(unreachable)
        return self

    def _require_response_fields(self) -> None:
        required = (
            self.session_index,
            self.agent_step,
            self.model_revision,
            self.response_token_usage,
            self.response_estimated_cost_usd,
        )
        if any(item is None for item in required):
            self._invalid("响应事件必须保存 Session、Step、模型 revision 和本次用量")
        if self.terminal_status is not None or self.stop_detail is not None:
            self._invalid("响应事件不得声明 Trial 终态")

    def _require_terminal_fields(self) -> None:
        if self.terminal_status is None:
            self._invalid("终态事件必须声明 terminal_status")
        if self.response_token_usage is not None:
            self._invalid("终态事件的本次 Token 必须为 N/A")
        if self.response_estimated_cost_usd is not None:
            self._invalid("终态事件的本次费用必须为 N/A")

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16d2_canary_usage_event_invalid", detail)


def usage_status(api_call_count: int, response_count: int) -> ActualUsageStatus:
    """按调用数与已观察响应数机械分类用量完整性。"""
    if response_count == 0:
        return ActualUsageStatus.NOT_AVAILABLE
    if response_count < api_call_count:
        return ActualUsageStatus.PARTIAL
    return ActualUsageStatus.COMPLETE


@dataclass(frozen=True, slots=True)
class LiveCanaryUsageStoreError(RuntimeError):
    """Canary 用量日志无法创建、追加或严格读取。"""

    detail: str

    def __str__(self) -> str:
        """返回不含模型正文或凭据的稳定诊断。"""
        return self.detail


@dataclass(frozen=True, slots=True)
class LiveCanaryMetadataDriftError(RuntimeError):
    """响应已落盘，但 Provider 或模型元数据偏离冻结配置。"""

    detail: str

    def __str__(self) -> str:
        """返回不含模型正文或凭据的稳定诊断。"""
        return self.detail


@dataclass(frozen=True, slots=True)
class CanaryUsageSnapshot:
    """Tracker 提交给 Journal 的完整原子快照。"""

    event_type: Literal["response", "terminal"]
    trial_id: str
    condition_id: str
    session_index: int | None
    agent_step: int | None
    provider: str
    model_id: str
    model_revision: str | None
    api_call_count: int
    response_count: int
    total_reserved_usd: Decimal
    run_reserved_usd: Decimal
    response_token_usage: TokenUsage | None
    response_estimated_cost_usd: Decimal | None
    observed_token_usage: TokenUsage | None
    observed_estimated_cost_usd: Decimal | None
    completed_session_indices: tuple[int, ...]
    terminal_status: LiveTrialTerminalStatus | None = None
    stop_detail: str | None = None


class CanaryUsageSink(Protocol):
    """Tracker 所需的最小追加接口，避免状态机与文件存储循环依赖。"""

    @property
    def expected_provider(self) -> str:
        """冻结 Provider。"""
        ...

    @property
    def expected_model_id(self) -> str:
        """冻结模型 ID。"""
        ...

    def append_snapshot(self, snapshot: CanaryUsageSnapshot) -> CanaryUsageJournalEvent:
        """同步保存一个响应或终态快照。"""
        ...
