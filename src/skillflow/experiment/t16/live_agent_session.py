"""T16-C 单 Session 的 Responses Tool loop。"""

from dataclasses import dataclass
from decimal import Decimal

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent_calls import (
    ActualUsageCheckpoint,
    BudgetCheckpoint,
    CallPersistence,
    InputTokenBoundTracker,
    LiveAgentClient,
    invoke_with_retry,
)
from skillflow.experiment.t16.live_agent_tool_loop import ToolLoopContext, execute_tools
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.live_design_models import LiveSessionDesign
from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t16.live_records import LiveSessionRecord, LiveToolCallAudit
from skillflow.experiment.t16.live_session_finish import finish_session
from skillflow.experiment.t16.live_session_records import (
    ProviderFailureDiagnostic,
    SessionOutcome,
    SessionTelemetry,
    session_record,
)
from skillflow.experiment.t16.live_tools import LiveToolRuntime, live_tool_definitions
from skillflow.experiment.t16.openai_response_models import (
    JsonObject,
    OpenAIResponsesCall,
)
from skillflow.experiment.t16.provider import TokenUsage, estimate_result_cost
from skillflow.experiment.t16.task_success_output import StructuredTaskResultV3


@dataclass(frozen=True, slots=True)
class SessionExecution:
    """Session 记录和继续执行所需的预算、重试与 revision。"""

    record: LiveSessionRecord
    budget: BudgetLedger
    retry_events: tuple[str, ...]
    model_revision: str | None
    structured_task_result: StructuredTaskResultV3 | None = None


@dataclass(frozen=True, slots=True)
class SessionRuntimeContext:
    """所有 Session 共享且不会被模型修改的运行依赖。"""

    config: T16CLiveConfig
    client: LiveAgentClient
    tools: LiveToolRuntime
    budget_checkpoint: BudgetCheckpoint | None = None
    usage_checkpoint: ActualUsageCheckpoint | None = None


def execute_session(
    design: LiveSessionDesign,
    context: SessionRuntimeContext,
    budget: BudgetLedger,
) -> SessionExecution:
    """执行一个无状态续传的 Responses Tool loop。"""
    history: list[JsonObject] = list(design.input_items)
    audits: list[LiveToolCallAudit] = []
    usage = zero_usage()
    latency = 0
    cost = Decimal(0)
    calls = 0
    retries: list[str] = []
    revision: str | None = None
    input_bounds = InputTokenBoundTracker(context.config)
    while True:
        call = OpenAIResponsesCall(
            model=context.config.provider.model_id,
            temperature=context.config.provider.temperature,
            reasoning_effort=context.config.provider.reasoning_effort,
            max_output_tokens=context.config.budget.max_output_tokens_per_turn,
            input_items=tuple(history),
            tools=live_tool_definitions(tuple(item.value for item in design.tool_names)),
            output_contract=design.output_contract,
            prompt_cache_mode=context.config.prompt_cache_mode,
        )
        called = invoke_with_retry(
            call,
            context.config,
            context.client,
            budget,
            CallPersistence(
                context.budget_checkpoint,
                context.usage_checkpoint,
                input_bounds,
            ),
        )
        budget = called.budget
        calls += called.api_call_count
        retries.extend(called.retry_events)
        if called.turn is None:
            telemetry = _telemetry(usage, calls, latency, cost, tuple(audits))
            record = session_record(
                design.session_index,
                telemetry,
                SessionOutcome(called.failure or SessionOutcome.PROVIDER_ERROR.value),
                provider_diagnostic=ProviderFailureDiagnostic(
                    status_code=called.failure_status_code,
                    error_type=called.failure_provider_type,
                    error_code=called.failure_provider_code,
                    error_param=called.failure_provider_param,
                ),
            )
            return SessionExecution(record, budget, tuple(retries), revision)
        turn = called.turn
        usage = add_usage(usage, turn.token_usage)
        latency += turn.latency_ms
        cost += estimate_result_cost(context.config.provider.pricing, turn.token_usage)
        if revision is not None and revision != turn.model_revision:
            telemetry = _telemetry(usage, calls, latency, cost, tuple(audits))
            record = session_record(
                design.session_index,
                telemetry,
                SessionOutcome.SCHEMA_REJECTION,
            )
            return SessionExecution(record, budget, tuple(retries), revision)
        revision = turn.model_revision
        if turn.refusal:
            telemetry = _telemetry(usage, calls, latency, cost, tuple(audits))
            record = session_record(
                design.session_index,
                telemetry,
                SessionOutcome.REFUSAL,
            )
            return SessionExecution(record, budget, tuple(retries), revision)
        if turn.function_calls:
            rejected = execute_tools(
                turn,
                ToolLoopContext(design.session_index, context.tools, history, audits),
            )
            if rejected:
                telemetry = _telemetry(usage, calls, latency, cost, tuple(audits))
                record = session_record(
                    design.session_index,
                    telemetry,
                    SessionOutcome.SCHEMA_REJECTION,
                )
                return SessionExecution(record, budget, tuple(retries), revision)
            continue
        telemetry = _telemetry(usage, calls, latency, cost, tuple(audits))
        finished = finish_session(design, turn, telemetry)
        return SessionExecution(
            finished.record,
            budget,
            tuple(retries),
            revision,
            finished.structured_task_result,
        )


def _telemetry(
    usage: TokenUsage,
    calls: int,
    latency: int,
    cost: Decimal,
    audits: tuple[LiveToolCallAudit, ...],
) -> SessionTelemetry:
    return SessionTelemetry(usage, calls, latency, cost, audits)
