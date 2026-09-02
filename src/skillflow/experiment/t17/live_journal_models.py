"""T17 Live 用量哈希链的事件、绑定与强类型错误。"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.live_attempt_models import (
    T17LiveFailureKind,
    T17LiveTerminalStatus,
    T17LiveUnitKind,
    T17ProviderFailureDiagnostic,
)
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class T17LiveJournalEvent(StrictModel):
    """不含 Prompt、响应正文或凭据的一条追加式实际用量事件。"""

    schema_version: Literal["0.1"] = "0.1"
    sequence: PositiveInt
    event_type: Literal["attempt", "response", "terminal"]
    phase_contract_sha256: Sha256Hex
    approved_config_sha256: Sha256Hex
    stage: T17LiveStage
    unit_id: NonEmptyStr
    trial_id: NonEmptyStr
    unit_kind: T17LiveUnitKind
    api_call_count: NonNegativeInt
    response_count: NonNegativeInt
    total_reserved_usd: NonNegativeMoney
    run_reserved_usd: NonNegativeMoney
    actual_usage_status: MeasurementStatus
    observed_token_usage: TokenUsage | None
    observed_estimated_cost_usd: NonNegativeMoney | None
    provider: Literal["openai"]
    expected_model_id: NonEmptyStr
    expected_model_revision: NonEmptyStr
    actual_model_revision: NonEmptyStr | None = None
    latency_ms: NonNegativeInt = 0
    agent_step_count: NonNegativeInt = 0
    retry_count: NonNegativeInt = 0
    refusal_count: NonNegativeInt = 0
    no_call_count: NonNegativeInt = 0
    terminal_status: T17LiveTerminalStatus | None = None
    failure_kind: T17LiveFailureKind | None = None
    failure_detail: NonEmptyStr | None = None
    failure_diagnostic: T17ProviderFailureDiagnostic | None = None
    previous_event_sha256: Sha256Hex | None = None
    event_sha256: Sha256Hex

    @model_validator(mode="after")
    def require_event_contract(self) -> Self:
        """依次验证实际用量、终态和模型 revision 合同。"""
        self._require_usage_contract()
        self._require_terminal_contract()
        self._require_revision_contract()
        return self

    def _require_usage_contract(self) -> None:
        if self.response_count > self.api_call_count:
            self._invalid("response_count 不能大于 api_call_count")
        if self.actual_usage_status is not journal_usage_status(
            self.api_call_count,
            self.response_count,
        ):
            self._invalid("actual_usage_status 与调用/响应计数不一致")
        has_usage = (
            self.observed_token_usage is not None and self.observed_estimated_cost_usd is not None
        )
        if (self.response_count > 0) is not has_usage:
            self._invalid("实际响应与 Token/费用存在性不一致")

    def _require_terminal_contract(self) -> None:
        terminal_values = (
            self.terminal_status,
            self.failure_kind,
            self.failure_detail,
            self.failure_diagnostic,
        )
        if self.event_type != "terminal":
            if any(value is not None for value in terminal_values):
                self._invalid("中间事件不得声明终态")
            return
        if self.terminal_status is None:
            self._invalid("终态事件必须声明 terminal_status")
        completed = self.terminal_status is T17LiveTerminalStatus.COMPLETED
        if completed is (self.failure_kind is not None):
            self._invalid("完成状态与 failure_kind 不一致")
        if completed and self.failure_diagnostic is not None:
            self._invalid("完成事件不得包含 Provider failure diagnostic")

    def _require_revision_contract(self) -> None:
        if self.event_type == "attempt" and self.actual_model_revision is not None:
            self._invalid("调用前事件不得伪造实际模型 revision")
        if self.event_type == "response" and self.actual_model_revision is None:
            self._invalid("响应事件必须保存实际模型 revision")

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t17_live_journal_event_invalid", detail)


@dataclass(frozen=True, slots=True)
class T17LiveJournalBinding:
    """所有事件共享的阶段合同与冻结模型身份。"""

    phase_contract_sha256: str
    approved_config_sha256: str
    stage: T17LiveStage
    model_id: str
    model_revision: str


@dataclass(frozen=True, slots=True)
class T17JournalTerminal:
    """Tracker 写入终态所需的状态与安全失败字段。"""

    status: T17LiveTerminalStatus
    failure_kind: T17LiveFailureKind | None = None
    failure_detail: str | None = None
    failure_diagnostic: T17ProviderFailureDiagnostic | None = None


@unique
class T17LiveJournalErrorCode(StrEnum):
    """Journal 生命周期和完整性错误。"""

    OPEN_FAILED = "open_failed"
    NOT_OPEN = "not_open"
    UNIT_TERMINAL = "unit_terminal"
    APPEND_FAILED = "append_failed"
    UNIT_FINALIZED = "unit_finalized"
    READ_FAILED = "read_failed"
    CHAIN_INVALID = "chain_invalid"
    HASH_INVALID = "hash_invalid"


class T17LiveJournalError(RuntimeError):
    """实际用量日志无法安全创建、追加或验证。"""

    __slots__ = ("code", "identifier")

    def __init__(
        self,
        code: T17LiveJournalErrorCode,
        identifier: str | None = None,
    ) -> None:
        """保存封闭错误码，同时保留 Exception traceback 可写语义。"""
        super().__init__(code.value, identifier)
        self.code = code
        self.identifier = identifier

    def __str__(self) -> str:
        """返回不含秘密和正文的稳定诊断。"""
        suffix = "" if self.identifier is None else f":{self.identifier}"
        return f"{self.code.value}{suffix}"


class T17ModelRevisionDriftError(RuntimeError):
    """响应 revision 与冻结 revision 不一致。"""

    __slots__ = ("actual", "expected")

    def __init__(self, expected: str, actual: str) -> None:
        """保存冻结与实际 revision，不冻结 Exception 内部状态。"""
        super().__init__(expected, actual)
        self.expected = expected
        self.actual = actual

    def __str__(self) -> str:
        """返回模型版本漂移，不包含正文。"""
        return f"model_revision_changed:{self.expected}:{self.actual}"


def journal_usage_status(api_calls: int, responses: int) -> MeasurementStatus:
    """从调用与响应计数机械确定实际用量覆盖状态。"""
    if responses == 0:
        return MeasurementStatus.NOT_AVAILABLE
    if responses < api_calls:
        return MeasurementStatus.INCOMPLETE
    return MeasurementStatus.MEASURED
