"""T16-C 单次 Responses 调用的预留预算与有限重试。"""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

from skillflow.experiment.t16.budget import BudgetLedger, CallReservation
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.openai_response_models import OpenAIResponsesCall
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
    OpenAIResponsesSchemaError,
    OpenAIResponsesTurn,
)
from skillflow.experiment.t16.provider import (
    ProviderRequest,
    TokenUsage,
    estimate_reservation_cost,
    estimate_result_cost,
)

HTTP_SERVER_ERROR_MIN = 500


class LiveAgentClient(Protocol):
    """真实与脚本 Client 共享的单轮 Responses 接口。"""

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        """生成一次模型轮次。"""
        ...


class BudgetCheckpoint(Protocol):
    """调用前预算占用的持久化边界。"""

    def record(self, budget: BudgetLedger) -> None:
        """在网络调用前同步保存最新预算。"""
        ...


class ActualUsageCheckpoint(Protocol):
    """调用尝试与实际响应的即时累计边界。"""

    def record_attempt(self, budget: BudgetLedger) -> None:
        """在 Client 调用前累计一次已预留的尝试。"""
        ...

    def record_response(self, usage: TokenUsage, estimated_cost_usd: Decimal) -> None:
        """Client 响应一返回即保存实际 Token 与费用。"""
        ...


@dataclass(frozen=True, slots=True)
class ActualResponseUsage:
    """一次已返回响应的即时用量与冻结 Provider 元数据。"""

    token_usage: TokenUsage
    estimated_cost_usd: Decimal
    provider: Literal["openai"]
    model_id: str
    model_revision: str
    budget: BudgetLedger | None = None


@runtime_checkable
class DetailedActualUsageCheckpoint(Protocol):
    """需要逐响应 Provider/model 元数据的持久化边界。"""

    def record_detailed_response(self, response: ActualResponseUsage) -> None:
        """立即保存一次响应及其 Provider/model 元数据。"""
        ...


@runtime_checkable
class SessionAwareUsageCheckpoint(ActualUsageCheckpoint, Protocol):
    """让 Trial 级用量累计器绑定当前 Session。"""

    def activate_session(self, session_index: int) -> None:
        """在 Session 首次模型调用前绑定 Session。"""
        ...

    def complete_session(self, session_index: int) -> None:
        """在 Session 记录构造完成后保存完成边界。"""
        ...


class InputTokenBoundTracker:
    """用实际输入 Token 与载荷差分收紧后续调用上界。"""

    __slots__ = ("config", "previous_input_tokens", "previous_payload")

    def __init__(self, config: T16CLiveConfig) -> None:
        """初始化尚无 Provider 观察值的边界状态。"""
        self.config = config
        self.previous_payload: bytes | None = None
        self.previous_input_tokens: int | None = None

    def estimate(self, payload_text: str) -> int:
        """首次保持完整字节上界；之后只为变化区间保守加量。"""
        payload = payload_text.encode()
        full_bound = len(payload) + 256
        if (
            not self.config.reuse_observed_input_tokens
            or self.previous_payload is None
            or self.previous_input_tokens is None
        ):
            return full_bound
        prefix = _common_prefix_length(self.previous_payload, payload)
        suffix = _common_suffix_length(self.previous_payload, payload, prefix)
        changed = len(self.previous_payload) + len(payload) - (2 * prefix) - (2 * suffix)
        return min(full_bound, self.previous_input_tokens + changed + 256)

    def observe(self, payload_text: str, input_tokens: int) -> None:
        """成功响应后保存 Provider 实际输入量与对应请求载荷。"""
        self.previous_payload = payload_text.encode()
        self.previous_input_tokens = input_tokens


@dataclass(frozen=True, slots=True)
class CallPersistence:
    """一次调用链的调用前预算与调用后实际用量持久化边界。"""

    budget: BudgetCheckpoint | None = None
    usage: ActualUsageCheckpoint | None = None
    input_bounds: InputTokenBoundTracker | None = None


@dataclass(frozen=True, slots=True)
class _ResponseAccounting:
    """一次已返回响应的预算结算和持久化上下文。"""

    config: T16CLiveConfig
    budget: BudgetLedger
    reservation: CallReservation
    persistence: CallPersistence | None
    payload_text: str
    input_bound: int
    output_bound: int


@dataclass(frozen=True, slots=True)
class CallExecution:
    """单个逻辑调用在有限重试后的结果。"""

    turn: OpenAIResponsesTurn | None
    budget: BudgetLedger
    api_call_count: int
    retry_events: tuple[str, ...]
    failure: str | None = None
    failure_status_code: int | None = None
    failure_provider_type: str | None = None
    failure_provider_code: str | None = None
    failure_provider_param: str | None = None


def invoke_with_retry(
    call: OpenAIResponsesCall,
    config: T16CLiveConfig,
    client: LiveAgentClient,
    budget: BudgetLedger,
    persistence: CallPersistence | None = None,
) -> CallExecution:
    """每次尝试先保守预留；全 Trial 最多使用配置中的一次重试。"""
    attempts = 0
    events: list[str] = []
    while True:
        payload_text = json.dumps(call.payload(), ensure_ascii=False, separators=(",", ":"))
        input_bound = (
            persistence.input_bounds.estimate(payload_text)
            if persistence is not None and persistence.input_bounds is not None
            else len(payload_text.encode()) + 256
        )
        request = ProviderRequest(
            input_text=payload_text,
            estimated_input_tokens=input_bound,
            max_output_tokens=call.max_output_tokens,
        )
        reservation = CallReservation(
            estimated_cost_usd=estimate_reservation_cost(config.provider, request),
            max_output_tokens=call.max_output_tokens,
        )
        budget = budget.authorize_call(reservation)
        if persistence is not None and persistence.budget is not None:
            persistence.budget.record(budget)
        if persistence is not None and persistence.usage is not None:
            persistence.usage.record_attempt(budget)
        attempts += 1
        try:
            turn = client.create(call)
        except OpenAIResponsesError as error:
            if not _is_retryable(error) or budget.retries >= config.budget.max_retries:
                return CallExecution(
                    None,
                    budget,
                    attempts,
                    tuple(events),
                    error.kind.value,
                    error.status_code,
                    error.provider_type,
                    error.provider_code,
                    error.provider_param,
                )
            budget = budget.record_retry()
            events.append(error.kind.value)
            continue
        except OpenAIResponsesSchemaError:
            return CallExecution(None, budget, attempts, tuple(events), "schema_rejection")
        budget, usage_within_bound = _account_response(
            turn,
            _ResponseAccounting(
                config,
                budget,
                reservation,
                persistence,
                payload_text,
                input_bound,
                call.max_output_tokens,
            ),
        )
        if not usage_within_bound:
            return CallExecution(None, budget, attempts, tuple(events), "schema_rejection")
        return CallExecution(turn, budget, attempts, tuple(events))


def _account_response(
    turn: OpenAIResponsesTurn,
    context: _ResponseAccounting,
) -> tuple[BudgetLedger, bool]:
    """立即记录响应，并在用量受限时把预留结算为实际费用。"""
    cost = estimate_result_cost(context.config.provider.pricing, turn.token_usage)
    persistence = context.persistence
    if persistence is not None and persistence.input_bounds is not None:
        persistence.input_bounds.observe(context.payload_text, turn.token_usage.input_tokens)
    usage_within_bound = _usage_within_bound(
        turn.token_usage,
        context.input_bound,
        context.output_bound,
    )
    budget = context.budget
    if usage_within_bound:
        budget = context.config.settle_call_budget(budget, context.reservation, cost)
    if persistence is not None and persistence.usage is not None:
        checkpoint = persistence.usage
        if isinstance(checkpoint, DetailedActualUsageCheckpoint):
            checkpoint.record_detailed_response(
                ActualResponseUsage(
                    token_usage=turn.token_usage,
                    estimated_cost_usd=cost,
                    provider="openai",
                    model_id=context.config.provider.model_id,
                    model_revision=turn.model_revision,
                    budget=budget,
                )
            )
        else:
            checkpoint.record_response(turn.token_usage, cost)
    return budget, usage_within_bound


def _usage_within_bound(usage: TokenUsage, input_bound: int, output_bound: int) -> bool:
    return (
        usage.input_tokens <= input_bound
        and usage.output_tokens + usage.reasoning_tokens <= output_bound
    )


def _is_retryable(error: OpenAIResponsesError) -> bool:
    """只重试瞬态错误；确定性的 4xx Provider 错误立即停止。"""
    if error.kind in {
        OpenAIResponsesErrorKind.TIMEOUT,
        OpenAIResponsesErrorKind.RATE_LIMIT,
    }:
        return True
    return error.status_code is None or error.status_code >= HTTP_SERVER_ERROR_MIN


def _common_prefix_length(left: bytes, right: bytes) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _common_suffix_length(left: bytes, right: bytes, prefix: int) -> int:
    limit = min(len(left), len(right)) - prefix
    index = 0
    while index < limit and left[-(index + 1)] == right[-(index + 1)]:
        index += 1
    return index
