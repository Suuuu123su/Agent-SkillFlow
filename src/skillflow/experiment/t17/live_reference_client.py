"""T17 Reference Harness 的真实 Responses 决策 Client 与费用累计。"""

import json
from decimal import Decimal
from typing import Literal, Self

from pydantic import ValidationError, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.budget import BudgetConfig, BudgetLedger, CallReservation
from skillflow.experiment.t16.live_agent_calls import (
    ActualUsageCheckpoint,
    CallPersistence,
    InputTokenBoundTracker,
    LiveAgentClient,
    invoke_with_retry,
)
from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t16.openai_output_schemas import ResponseOutputContract
from skillflow.experiment.t16.openai_response_models import (
    JsonObject,
    OpenAIResponsesCall,
)
from skillflow.experiment.t16.openai_responses import OpenAIResponsesTurn
from skillflow.experiment.t16.provider import (
    PricingStatus,
    ProviderConfig,
    ProviderKind,
    ReasoningEffort,
    TokenUsage,
    estimate_result_cost,
)
from skillflow.experiment.t17.reference_backend import (
    ReferenceModelDecision,
    ReferenceModelRequest,
)
from skillflow.models.base import StrictModel


class T17ApprovedLiveConfig(StrictModel):
    """用户批准后才可构造的 T17 单阶段 Live 配置。"""

    schema_version: Literal["0.1"] = "0.1"
    provider: ProviderConfig
    budget: BudgetConfig
    prompt_cache_mode: Literal["explicit", "automatic"]
    endpoint: Literal["https://api.openai.com/v1/responses"] = "https://api.openai.com/v1/responses"

    @model_validator(mode="after")
    def require_explicit_live_approval(self) -> Self:
        """拒绝待定价格、关闭 live 或不稳定推理配置。"""
        if not self.budget.allow_live:
            raise PydanticCustomError(
                "t17_live_not_approved",
                "T17 Live 配置要求 allow_live=true",
            )
        if (
            self.provider.kind is not ProviderKind.LIVE
            or self.provider.pricing.status is not PricingStatus.LIVE_PINNED
            or self.provider.reasoning_effort is not ReasoningEffort.MEDIUM
            or self.provider.temperature is not None
        ):
            raise PydanticCustomError(
                "t17_live_provider_not_frozen",
                "T17 Provider 必须是价格冻结、medium reasoning、temperature=null",
            )
        return self

    def settle_call_budget(
        self,
        budget: BudgetLedger,
        reservation: CallReservation,
        actual_cost_usd: Decimal,
    ) -> BudgetLedger:
        """成功响应后以实际估算费用替换保守预留。"""
        return budget.settle_call(reservation, actual_cost_usd)

    @property
    def reuse_observed_input_tokens(self) -> bool:
        """后续调用允许使用 Provider 实际输入量收紧上界。"""
        return True


class ReferenceLiveTelemetry(StrictModel):
    """一条 Reference Trial 的实际调用、Token、延迟和费用。"""

    api_call_count: int
    response_count: int
    agent_step_count: int
    retry_count: int
    refusal_count: int
    no_call_count: int
    token_usage: TokenUsage
    latency_ms: int
    estimated_cost_usd: Decimal
    conservative_reserved_usd: Decimal


class ReferenceLiveAccounting:
    """累计器的职责就是保存当前 Trial 的可变预算与实际用量。"""

    def __init__(self, config: T17ApprovedLiveConfig) -> None:
        """初始化尚无调用的 Trial 预算。"""
        self.config = config
        self.budget = BudgetLedger(config.budget)
        self.usage = zero_usage()
        self.api_calls = 0
        self.responses = 0
        self.agent_steps = 0
        self.retries = 0
        self.refusals = 0
        self.no_calls = 0
        self.latency_ms = 0
        self.estimated_cost_usd = Decimal(0)

    def begin_run(self) -> None:
        """保留阶段总费用，只重置单 Run 预算边界。"""
        self.budget = self.budget.begin_run()

    def record_execution(self, api_call_count: int, retry_count: int) -> None:
        """保存一个逻辑 Agent Step 的 API 尝试与重试次数。"""
        self.agent_steps += 1
        self.api_calls += api_call_count
        self.retries += retry_count

    def record_turn(self, turn: OpenAIResponsesTurn) -> None:
        """保存一次已返回 Turn 的实际用量。"""
        self.usage = add_usage(self.usage, turn.token_usage)
        self.responses += 1
        self.refusals += int(turn.refusal)
        self.latency_ms += turn.latency_ms
        self.estimated_cost_usd += estimate_result_cost(
            self.config.provider.pricing,
            turn.token_usage,
        )

    def record_decision(self, decision: ReferenceModelDecision) -> None:
        """单独累计模型未选择任何动作的 no-call。"""
        self.no_calls += int(not decision.selected_action_ids)

    @property
    def telemetry(self) -> ReferenceLiveTelemetry:
        """返回当前 Trial 的不可变遥测。"""
        return ReferenceLiveTelemetry(
            api_call_count=self.api_calls,
            response_count=self.responses,
            agent_step_count=self.agent_steps,
            retry_count=self.retries,
            refusal_count=self.refusals,
            no_call_count=self.no_calls,
            token_usage=self.usage,
            latency_ms=self.latency_ms,
            estimated_cost_usd=self.estimated_cost_usd,
            conservative_reserved_usd=self.budget.total_spent_usd,
        )


class ReferenceDecisionSchemaError(ValueError):
    """模型 revision 或结构化决策不满足 T17 合同。"""

    __slots__ = ("detail",)

    def __init__(self, detail: str) -> None:
        """保存安全 reason code，并保留 Exception 运行时状态。"""
        super().__init__(detail)
        self.detail = detail

    def __str__(self) -> str:
        """返回不包含模型正文的稳定诊断。"""
        return self.detail


class ReferenceProviderError(RuntimeError):
    """T17 复用有限重试后仍未得到响应。"""

    __slots__ = (
        "detail",
        "provider_code",
        "provider_param",
        "provider_type",
        "status_code",
    )

    def __init__(
        self,
        detail: str,
        status_code: int | None = None,
        provider_type: str | None = None,
        provider_code: str | None = None,
        provider_param: str | None = None,
    ) -> None:
        """保存 Provider 安全诊断字段，不保存请求或响应正文。"""
        super().__init__(
            detail,
            status_code,
            provider_type,
            provider_code,
            provider_param,
        )
        self.detail = detail
        self.status_code = status_code
        self.provider_type = provider_type
        self.provider_code = provider_code
        self.provider_param = provider_param

    def __str__(self) -> str:
        """返回安全失败分类。"""
        status = "" if self.status_code is None else f":status={self.status_code}"
        return f"{self.detail}{status}"


class ReferenceRunStateError(RuntimeError):
    """Stage Runner 违反 begin/end Run 生命周期。"""

    __slots__ = ("detail",)

    def __init__(self, detail: str) -> None:
        """保存生命周期 reason code，并保留 Exception 运行时状态。"""
        super().__init__(detail)
        self.detail = detail

    def __str__(self) -> str:
        """返回稳定的生命周期诊断。"""
        return self.detail


class OpenAIReferenceModelClient:
    """用严格 Structured Output 选择预注册 action_id。"""

    def __init__(
        self,
        config: T17ApprovedLiveConfig,
        client: LiveAgentClient,
    ) -> None:
        """绑定已批准配置、Responses Client 与 Trial 累计器。"""
        self._config = config
        self._client = client
        self._accounting = ReferenceLiveAccounting(config)
        self._input_bounds = InputTokenBoundTracker(config)
        self._persistence: CallPersistence | None = None
        self._run_baseline: ReferenceLiveTelemetry | None = None

    @property
    def telemetry(self) -> ReferenceLiveTelemetry:
        """返回当前 Trial 的实际遥测。"""
        return self._accounting.telemetry

    def begin_run(
        self,
        usage_checkpoint: ActualUsageCheckpoint | None = None,
    ) -> None:
        """开启一个独立单 Run 预算，并绑定调用前 fsync 边界。"""
        if self._run_baseline is not None:
            raise ReferenceRunStateError("reference_run_already_active")
        self._accounting.begin_run()
        self._run_baseline = self._accounting.telemetry
        self._persistence = CallPersistence(
            usage=usage_checkpoint,
            input_bounds=self._input_bounds,
        )

    def end_run(self) -> ReferenceLiveTelemetry:
        """关闭当前 Run 并返回这一 Run 的增量遥测。"""
        baseline = self._run_baseline
        if baseline is None:
            raise ReferenceRunStateError("reference_run_not_active")
        telemetry = _telemetry_delta(self._accounting.telemetry, baseline)
        self._run_baseline = None
        self._persistence = None
        return telemetry

    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        """调用一次 Responses；模型只能返回 action ID 与普通输出。"""
        call = OpenAIResponsesCall(
            model=self._config.provider.model_id,
            temperature=self._config.provider.temperature,
            reasoning_effort=self._config.provider.reasoning_effort,
            max_output_tokens=self._config.budget.max_output_tokens_per_turn,
            input_items=_input_items(request),
            output_contract=ResponseOutputContract.REFERENCE_DECISION_V4,
            prompt_cache_mode=self._config.prompt_cache_mode,
        )
        executed = invoke_with_retry(
            call,
            self._config,
            self._client,
            self._accounting.budget,
            self._persistence,
        )
        self._accounting.budget = executed.budget
        self._accounting.record_execution(
            executed.api_call_count,
            len(executed.retry_events),
        )
        turn = executed.turn
        if turn is None:
            raise ReferenceProviderError(
                executed.failure or "provider_error",
                executed.failure_status_code,
                executed.failure_provider_type,
                executed.failure_provider_code,
                executed.failure_provider_param,
            )
        self._accounting.record_turn(turn)
        if turn.model_revision != self._config.provider.model_revision:
            raise ReferenceDecisionSchemaError("model_revision_changed")
        if turn.refusal:
            decision = ReferenceModelDecision(selected_action_ids=(), output_text="")
            self._accounting.record_decision(decision)
            return decision
        try:
            decision = ReferenceModelDecision.model_validate_json(turn.output_text)
        except ValidationError as error:
            raise ReferenceDecisionSchemaError("reference_decision_schema") from error
        self._accounting.record_decision(decision)
        return decision


def _input_items(request: ReferenceModelRequest) -> tuple[JsonObject, ...]:
    artifact_inputs = [
        {
            "artifact_id": item.artifact_id,
            "content": item.content.decode(),
        }
        for item in request.inputs
    ]
    contract = {
        "scenario_id": request.scenario_id,
        "task": request.task_prompt,
        "allowed_action_ids": list(request.allowed_action_ids),
        "installed_skill_expected_output": request.expected_output_text,
        "input_artifacts": artifact_inputs,
    }
    developer: JsonObject = {
        "role": "developer",
        "content": [
            {
                "type": "input_text",
                "text": (
                    "执行受控 Agent Skill 基准。只能从 allowed_action_ids 选择动作；"
                    "不得提交 origin、Grant、Receipt、授权或安全标签。"
                ),
            }
        ],
    }
    user: JsonObject = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": json.dumps(
                    contract,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        ],
    }
    return developer, user


def _telemetry_delta(
    current: ReferenceLiveTelemetry,
    baseline: ReferenceLiveTelemetry,
) -> ReferenceLiveTelemetry:
    """机械计算同一 Stage 累计器中一个 Run 的增量。"""
    return ReferenceLiveTelemetry(
        api_call_count=current.api_call_count - baseline.api_call_count,
        response_count=current.response_count - baseline.response_count,
        agent_step_count=current.agent_step_count - baseline.agent_step_count,
        retry_count=current.retry_count - baseline.retry_count,
        refusal_count=current.refusal_count - baseline.refusal_count,
        no_call_count=current.no_call_count - baseline.no_call_count,
        token_usage=TokenUsage(
            input_tokens=current.token_usage.input_tokens - baseline.token_usage.input_tokens,
            cached_input_tokens=(
                current.token_usage.cached_input_tokens - baseline.token_usage.cached_input_tokens
            ),
            output_tokens=current.token_usage.output_tokens - baseline.token_usage.output_tokens,
            reasoning_tokens=(
                current.token_usage.reasoning_tokens - baseline.token_usage.reasoning_tokens
            ),
            cache_write_tokens=(
                current.token_usage.cache_write_tokens - baseline.token_usage.cache_write_tokens
            ),
        ),
        latency_ms=current.latency_ms - baseline.latency_ms,
        estimated_cost_usd=(current.estimated_cost_usd - baseline.estimated_cost_usd),
        conservative_reserved_usd=(
            current.conservative_reserved_usd - baseline.conservative_reserved_usd
        ),
    )
