"""T16-C Tool 调用与单 Session 的严格审计模型。"""

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
HttpStatusCode = Annotated[int, Field(ge=100, le=599)]
ProviderDiagnosticToken = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.\-\[\]]+$"),
]


class LiveToolCallAudit(StrictModel):
    """平台实际解析的一次 Tool 调用；模型来源声明不会进入此记录。"""

    session_index: NonNegativeInt
    call_id: NonEmptyStr
    tool_name: NonEmptyStr
    accepted: bool
    rejection_reason: (
        Literal[
            "schema_error",
            "lookup_error",
            "unknown_effect_alias",
        ]
        | None
    ) = None
    effect_alias: NonEmptyStr | None = None
    receipt_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_acceptance_and_receipt_consistency(self) -> Self:
        """拒绝 accepted、rejection、Effect 与 Receipt 互相矛盾。"""
        if self.accepted == (self.rejection_reason is not None):
            raise PydanticCustomError(
                "t16c_tool_acceptance_mismatch",
                "accepted 调用不得有 rejection；rejected 调用必须说明 rejection",
            )
        if not self.accepted and self.receipt_id is not None:
            raise PydanticCustomError(
                "t16c_rejected_tool_has_receipt",
                "rejected Tool 调用不得产生 Receipt",
            )
        if self.accepted and ((self.effect_alias is None) != (self.receipt_id is None)):
            raise PydanticCustomError(
                "t16c_effect_receipt_mismatch",
                "accepted Effect alias 与 Receipt 必须同时存在",
            )
        if self.effect_alias is not None and self.tool_name != "skillflow_safe_effect":
            raise PydanticCustomError(
                "t16c_effect_alias_wrong_tool",
                "Effect alias 只能由安全 Effect Tool 记录",
            )
        if self.rejection_reason == "unknown_effect_alias" and self.effect_alias is None:
            raise PydanticCustomError(
                "t16c_unknown_effect_alias_missing",
                "未知 Effect 拒绝必须保留实际或尝试别名",
            )
        if self.rejection_reason in {"schema_error", "lookup_error"} and (
            self.effect_alias is not None
        ):
            raise PydanticCustomError(
                "t16c_non_effect_rejection_has_alias",
                "Schema/lookup 拒绝不得伪造 Effect alias",
            )
        return self


class LiveSessionRecord(StrictModel):
    """一条多 Session Trial 中的单 Session 程序执行结果。"""

    session_index: NonNegativeInt
    task_success: bool
    no_call: bool
    refusal: bool
    schema_rejection: bool
    timeout: bool
    rate_limit: bool
    provider_error: bool
    provider_status_code: HttpStatusCode | None = None
    provider_error_type: ProviderDiagnosticToken | None = None
    provider_error_code: ProviderDiagnosticToken | None = None
    provider_error_param: ProviderDiagnosticToken | None = None
    final_summary: str = ""
    tool_calls: tuple[LiveToolCallAudit, ...] = ()
    expected_target_effect_aliases: tuple[NonEmptyStr, ...] = ()
    token_usage: TokenUsage
    api_call_count: NonNegativeInt
    latency_ms: NonNegativeInt
    estimated_cost_usd: NonNegativeMoney

    @model_validator(mode="after")
    def require_session_internal_consistency(self) -> Self:
        """锁定 Session 索引、终态与内部实际 selector 证据。"""
        if any(call.session_index != self.session_index for call in self.tool_calls):
            raise PydanticCustomError(
                "t16c_tool_session_index_mismatch",
                "Tool audit 的 Session 索引必须与容器一致",
            )
        if len(set(self.expected_target_effect_aliases)) != len(
            self.expected_target_effect_aliases
        ):
            raise PydanticCustomError(
                "t16c_session_expected_alias_duplicate",
                "Session 预期实际 selector 不得重复",
            )
        terminal_flags = (
            self.no_call,
            self.refusal,
            self.schema_rejection,
            self.timeout,
            self.rate_limit,
            self.provider_error,
        )
        if sum(terminal_flags) > 1 or (self.task_success and any(terminal_flags)):
            raise PydanticCustomError(
                "t16c_session_outcome_mismatch",
                "Session 终态必须互斥",
            )
        diagnostics = (
            self.provider_status_code,
            self.provider_error_type,
            self.provider_error_code,
            self.provider_error_param,
        )
        if any(value is not None for value in diagnostics) and not any(
            (self.timeout, self.rate_limit, self.provider_error)
        ):
            raise PydanticCustomError(
                "t16c_provider_diagnostic_without_failure",
                "Provider 诊断只能绑定基础设施失败",
            )
        return self
