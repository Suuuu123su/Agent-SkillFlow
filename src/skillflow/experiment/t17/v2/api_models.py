"""第二版真实调用的授权、逐响应事实和安全失败类别。"""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self, runtime_checkable

from pydantic import Field, model_validator

from skillflow.experiment.t16.budget import BudgetConfig, BudgetLedger, CallReservation
from skillflow.experiment.t16.provider import (
    PricingStatus,
    ProviderConfig,
    ProviderKind,
    ReasoningEffort,
    TokenUsage,
)
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.reference_backend import ReferenceModelClient
from skillflow.experiment.t17.v2.run_models import PhaseContract, UnitUsage
from skillflow.models.base import NonEmptyStr, StrictModel


class CallIdentity(StrictModel):
    """调用前由受信执行器给出真实运行、会话、步骤与调用身份。"""

    run_id: NonEmptyStr
    session_id: NonEmptyStr
    step_id: NonEmptyStr
    call_id: NonEmptyStr


@runtime_checkable
class BoundReferenceClient(ReferenceModelClient, Protocol):
    """把 API 用量绑定到真实执行步骤，而非模型自报 ID。"""

    def bind_call(self, identity: CallIdentity) -> None:
        """只在请求前绑定受信上下文。"""
        ...


@runtime_checkable
class AccountingClient(ReferenceModelClient, Protocol):
    """真实调用必须实现的预算、阶段日志和逐单元用量边界。"""

    def authorized_for(self, matrix_sha256: str) -> bool:
        """仅批准的矩阵可开始新请求。"""
        ...

    def open_phase(self, output: Path, phase: PhaseContract) -> None:
        """请求前独占创建逐响应用量日志。"""
        ...

    def begin_unit(self, unit_id: str) -> None:
        """重置单任务用量而不重置阶段预算。"""
        ...

    def unit_usage(self) -> UnitUsage:
        """响应返回后已即时保存的累积用量。"""
        ...


class V2LiveConfig(StrictModel):
    """一次总预算批准分配出的阶段配置，不保存密钥。"""

    schema_version: Literal["2.0"] = "2.0"
    provider: ProviderConfig
    budget: BudgetConfig
    matrix_sha256: Sha256
    cost_plan_sha256: Sha256
    approval_id: NonEmptyStr
    prompt_cache_mode: Literal["explicit", "automatic"]
    max_input_bytes: Annotated[int, Field(ge=1024)] = 100000
    endpoint: Literal[
        "https://api.openai.com/v1/responses", "https://api.deepseek.com/responses"
    ] = "https://api.openai.com/v1/responses"

    @model_validator(mode="after")
    def validate_approval(self) -> Self:
        """价格使用冻结值，不再联网核价；预算和推理配置必须明确。"""
        if not self.budget.allow_live:
            raise ValueError("v2_live_not_authorized")
        deepseek = self.provider.model_id == "deepseek-v4-flash"
        if deepseek != (self.endpoint == "https://api.deepseek.com/responses"):
            raise ValueError("v2_provider_endpoint_mismatch")
        if (
            self.provider.kind is not ProviderKind.LIVE
            or self.provider.pricing.status is not PricingStatus.LIVE_PINNED
        ):
            raise ValueError("v2_provider_not_frozen")
        if (
            self.provider.temperature is not None
            or self.provider.reasoning_effort is not ReasoningEffort.MEDIUM
        ):
            raise ValueError("v2_reasoning_configuration_drift")
        return self

    def settle_call_budget(
        self, budget: BudgetLedger, reservation: CallReservation, actual_cost_usd: Decimal
    ) -> BudgetLedger:
        """实际用量确认后释放本次响应的多余预留。"""
        return budget.settle_call(reservation, actual_cost_usd)

    @property
    def reuse_observed_input_tokens(self) -> bool:
        """每次仍采用完整载荷字节上界，避免把经验估算当硬上限。"""
        return False


class ApiUsageEvent(StrictModel):
    """无正文、无凭据的追加式日志；响应行在解析模型内容前保存。"""

    schema_version: Literal["2.0"] = "2.0"
    sequence: Annotated[int, Field(ge=1)]
    event_type: Literal[
        "unit_start",
        "attempt",
        "response",
        "settlement",
        "transport_failure",
        "http_error",
        "model_failure",
        "revision_drift",
    ]
    phase_contract_sha256: Sha256
    matrix_sha256: Sha256
    unit_id: NonEmptyStr
    call: CallIdentity | None = None
    attempt_index: Annotated[int, Field(ge=0)]
    usage: TokenUsage | None = None
    response_id: NonEmptyStr | None = None
    model_revision: NonEmptyStr | None = None
    response_status: NonEmptyStr | None = None
    latency_ms: Annotated[int, Field(ge=0)] | None = None
    estimated_cost_usd: Annotated[Decimal, Field(ge=0)] | None = None
    total_reserved_usd: Annotated[Decimal, Field(ge=0)]
    unit_reserved_usd: Annotated[Decimal, Field(ge=0)]
    reason: NonEmptyStr | None = None
    previous_sha256: Sha256 | None
    event_sha256: Sha256

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        """响应不能遗漏用量、模型版本、延迟或实际运行绑定。"""
        if self.event_type == "response" and any(
            value is None
            for value in (
                self.call,
                self.usage,
                self.response_id,
                self.model_revision,
                self.response_status,
                self.latency_ms,
                self.estimated_cost_usd,
            )
        ):
            raise ValueError("v2_partial_response_record")
        if self.event_type == "attempt" and self.call is None:
            raise ValueError("v2_call_identity_missing")
        return self


class V2ProviderFailureError(OSError):
    """有限重试后仍未返回完整用量，阶段必须停止。"""


class V2RevisionDriftError(RuntimeError):
    """响应版本不同于冻结版本，保存用量后立即禁止新调用。"""


class V2UsageUnavailableError(OSError):
    """成功 HTTP 响应不能给出完整用量，不能伪造为零费用。"""


class V2UsageWriteFailureError(OSError):
    """无法同步保存预算或响应时禁止继续调用。"""


class V2BudgetExhaustedError(RuntimeError):
    """明确的请求前费用或用量门，不能误记为模型格式失败。"""
