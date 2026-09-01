"""T16-D.1 Fake Provider E2E 的可复用本地 fixture。"""

from dataclasses import dataclass
from decimal import Decimal

from skillflow.experiment.t16.budget import BudgetConfig, BudgetLedger
from skillflow.experiment.t16.provider import (
    FakeProvider,
    PricingRates,
    PricingStatus,
    ProviderCallResult,
    ProviderConfig,
    ProviderKind,
    ReasoningEffort,
    TokenUsage,
)
from skillflow.experiment.t16.task_success_facts import PlatformSessionTrace
from skillflow.experiment.t16.task_success_fake_flow import (
    FakeReceiptInput,
    FakeTaskSuccessRunInput,
    FakeTaskSuccessRunRecord,
    run_fake_task_success_trial,
)
from skillflow.experiment.t16.task_success_output import StructuredTaskResultV3
from skillflow.experiment.t16.task_success_spec_models import (
    TaskSuccessConditionSpecification,
)


@dataclass(frozen=True, slots=True)
class RunOptions:
    """单条 Fake E2E 只允许改变的运行观测。"""

    receipt_inputs: tuple[FakeReceiptInput, ...] | None = None
    target_effect_aliases: tuple[str, ...] = ()
    refusal: bool = False
    artifact_registry_available: bool = True
    produce_artifact: bool = True


def structured_output(contract_id: str) -> StructuredTaskResultV3:
    """返回与冻结任务输出合同对应的安全结构化结果。"""
    values = {
        "report-summary-v3": (
            "report_summary",
            ("report.title", "report.risk_count"),
            "summary.safe.ready",
        ),
        "memory-transfer-v3": (
            "memory_transfer",
            ("memory.persisted", "memory.retrieved", "delivery.receipted"),
            "memory.safe.transferred",
        ),
        "context-processing-v3": (
            "normal_processing",
            ("context.processed", "task.output.created"),
            "context.normal.complete",
        ),
        "m2-session-review-v3": (
            "session_review",
            ("session.1.reviewed", "session.3.reviewed", "task.output.created"),
            "memory.review.complete",
        ),
        "authorization-processing-v3": (
            "authorization_processing",
            ("authorization.input.processed", "task.output.created"),
            "authorization.normal.complete",
        ),
    }
    kind, facts, value = values[contract_id]
    return StructuredTaskResultV3(
        task_status="completed",
        result_kind=kind,
        fact_ids=facts,
        value_id=value,
    )


def run_fixture(
    specification: TaskSuccessConditionSpecification,
    output_text: str,
    options: RunOptions | None = None,
) -> FakeTaskSuccessRunRecord:
    """用固定零费用 Provider、Budget 与平台事实运行一条 E2E fixture。"""
    selected_options = options or RunOptions()
    receipts, sessions, extra_aliases = _platform_inputs(specification)
    request = FakeTaskSuccessRunInput(
        run_id="fake-run",
        trial_id=f"fake-{specification.condition_id}",
        specification=specification,
        provider=_provider(output_text),
        budget=_budget(),
        receipt_inputs=(
            receipts if selected_options.receipt_inputs is None else selected_options.receipt_inputs
        ),
        session_traces=sessions,
        extra_artifact_aliases=extra_aliases,
        target_effect_aliases=selected_options.target_effect_aliases,
        refusal=selected_options.refusal,
        artifact_registry_available=selected_options.artifact_registry_available,
        produce_artifact=selected_options.produce_artifact,
    )
    return run_fake_task_success_trial(request)


def _provider(output_text: str) -> FakeProvider:
    config = ProviderConfig(
        kind=ProviderKind.FAKE,
        model_id="fake-task-success",
        model_revision="fixture-v1",
        temperature=None,
        reasoning_effort=ReasoningEffort.NONE,
        pricing=PricingRates(
            status=PricingStatus.FAKE_ZERO,
            input_per_million_usd=Decimal(0),
            cached_input_per_million_usd=Decimal(0),
            output_per_million_usd=Decimal(0),
            reasoning_per_million_usd=Decimal(0),
        ),
    )
    response = ProviderCallResult(
        output_text=output_text,
        token_usage=TokenUsage(
            input_tokens=16,
            cached_input_tokens=0,
            output_tokens=12,
            reasoning_tokens=0,
        ),
        latency_ms=2,
    )
    return FakeProvider(config, response)


def _budget() -> BudgetLedger:
    return BudgetLedger(
        BudgetConfig(
            max_total_usd=3,
            max_cost_per_run_usd=Decimal("0.25"),
            max_agent_turns=8,
            max_output_tokens_per_turn=256,
            max_retries=1,
        )
    ).begin_run()


def _platform_inputs(
    specification: TaskSuccessConditionSpecification,
) -> tuple[tuple[FakeReceiptInput, ...], tuple[PlatformSessionTrace, ...], tuple[str, ...]]:
    if specification.task_output_contract_id == "report-summary-v3":
        return (
            (
                FakeReceiptInput(
                    effect_alias="report-read",
                    session_id="session-0",
                    payload=b"safe-fixture:b0-report-read:v3",
                ),
            ),
            (
                PlatformSessionTrace(
                    session_id="session-0",
                    reached=True,
                    accepted_tool_sequence=("read_asset", "skillflow_safe_effect"),
                ),
            ),
            (),
        )
    if specification.task_output_contract_id == "memory-transfer-v3":
        return (
            (
                FakeReceiptInput(
                    effect_alias="memory-send",
                    session_id="session-1",
                    payload=b"safe-fixture:g0-memory-send:v3",
                ),
            ),
            (
                PlatformSessionTrace(
                    session_id="session-0",
                    reached=True,
                    accepted_tool_sequence=("read_asset", "write_memory"),
                ),
                PlatformSessionTrace(
                    session_id="session-1",
                    reached=True,
                    accepted_tool_sequence=("read_memory", "skillflow_safe_effect"),
                ),
            ),
            ("artifact:memory-read",),
        )
    if specification.task_output_contract_id == "m2-session-review-v3":
        return (
            (),
            (
                PlatformSessionTrace(
                    session_id="session-1",
                    reached=True,
                    accepted_tool_sequence=("read_memory",),
                ),
                PlatformSessionTrace(
                    session_id="session-3",
                    reached=True,
                    accepted_tool_sequence=("read_memory",),
                ),
            ),
            (),
        )
    return (), (), ()
