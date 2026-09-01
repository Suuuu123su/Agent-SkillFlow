import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent_calls import LiveAgentClient
from skillflow.experiment.t16.openai_response_models import (
    ApiFunctionCall,
    JsonObject,
    OpenAIResponsesCall,
)
from skillflow.experiment.t16.openai_responses import OpenAIResponsesTurn
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_evidence import AssertionStatus
from skillflow.experiment.t16.task_success_live_agent import (
    TaskSuccessLiveExecution,
    TaskSuccessLiveExecutionOptions,
    execute_task_success_live_trial,
)
from skillflow.experiment.t16.task_success_live_config import build_t16d2_live_config
from skillflow.experiment.t16.task_success_live_design import (
    build_task_success_live_design,
)
from skillflow.experiment.t16.task_success_live_preflight import load_t16d2_inputs

ROOT = Path(__file__).parents[4]
NOW = datetime(2026, 8, 29, tzinfo=UTC)


def _usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=100,
        cached_input_tokens=20,
        cache_write_tokens=0,
        output_tokens=8,
        reasoning_tokens=4,
    )


def _tool_turn(name: str, arguments: JsonObject, ordinal: int) -> OpenAIResponsesTurn:
    function = ApiFunctionCall(
        type="function_call",
        id=f"fc-{ordinal}",
        call_id=f"call-{ordinal}",
        name=name,
        arguments=json.dumps(arguments),
        status="completed",
    )
    return OpenAIResponsesTurn(
        response_id=f"response-{ordinal}",
        model_revision="gpt-5.6-luna",
        status="completed",
        function_calls=(function,),
        continuation_items=(function.model_dump(mode="json"),),
        output_text="",
        refusal=False,
        token_usage=_usage(),
        latency_ms=3,
    )


def _v3_result(value_id: str = "summary.safe.ready") -> OpenAIResponsesTurn:
    return OpenAIResponsesTurn(
        response_id="response-final",
        model_revision="gpt-5.6-luna",
        status="completed",
        function_calls=(),
        continuation_items=(),
        output_text=json.dumps(
            {
                "schema_version": "3.0",
                "task_status": "completed",
                "result_kind": "report_summary",
                "fact_ids": ["report.title", "report.risk_count"],
                "value_id": value_id,
            }
        ),
        refusal=False,
        token_usage=_usage(),
        latency_ms=3,
    )


@dataclass
class ScriptedClient(LiveAgentClient):
    script: list[OpenAIResponsesTurn]

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        return self.script.pop(0)


def _b0_execution(value_id: str = "summary.safe.ready") -> TaskSuccessLiveExecution:
    inputs = load_t16d2_inputs(ROOT)
    trial = next(
        item
        for item in inputs.matrix.trials
        if item.condition_id == "b0"
        and item.semantic_instance_id.endswith("v01")
        and item.repeat_index == 1
    )
    design = build_task_success_live_design(inputs, trial)
    config = build_t16d2_live_config(ROOT)
    client = ScriptedClient(
        [
            _tool_turn("read_asset", {"asset_id": "report"}, 1),
            _tool_turn(
                "skillflow_safe_effect",
                {
                    "effect_alias": "operation-1",
                    "content": "safe-fixture:b0-report-read:v3",
                },
                2,
            ),
            _v3_result(value_id),
        ]
    )
    return execute_task_success_live_trial(
        design,
        next(item for item in inputs.registry.conditions if item.condition_id == "b0"),
        config,
        client,
        BudgetLedger(config.budget).begin_run(),
        TaskSuccessLiveExecutionOptions(
            run_id="run-d2-b0",
            created_at=NOW,
            phase_contract_sha256="1" * 64,
        ),
    )


def test_v3_live_trial_builds_platform_evidence_and_deterministic_success() -> None:
    execution = _b0_execution()

    assert execution.record.schema_version == "0.3"
    assert execution.record.result.task_success is True
    assert execution.record.result.target_effect_executed is True
    assert execution.record.task_success_result is not None
    assert execution.record.task_success_result.not_evaluable_assertion_ids == ()
    assert {item.assertion_status for item in execution.record.task_success_evidence} == {
        AssertionStatus.PASSED
    }
    assert len(execution.snapshot.artifacts) == 1
    assert len(execution.snapshot.receipts) == 1
    assert execution.snapshot.receipts[0].run_id == execution.record.run_id
    assert execution.record.result.receipt_id == execution.snapshot.receipts[0].receipt_id


def test_wrong_model_task_value_is_failed_not_technical_na() -> None:
    execution = _b0_execution("summary.wrong")

    assert execution.record.result.task_success is False
    assert execution.record.task_success_result is not None
    assert execution.record.task_success_result.failed_assertion_ids
    assert execution.record.task_success_result.not_evaluable_assertion_ids == ()
