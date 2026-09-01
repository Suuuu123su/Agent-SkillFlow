"""版本化 Session 终态解析；自然语言终态不进入平台证据。"""

from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from skillflow.experiment.t16.live_design_models import LiveSessionDesign
from skillflow.experiment.t16.live_records import LiveSessionRecord
from skillflow.experiment.t16.live_session_records import (
    SessionOutcome,
    SessionTelemetry,
    session_record,
)
from skillflow.experiment.t16.openai_output_schemas import ResponseOutputContract
from skillflow.experiment.t16.openai_responses import OpenAIResponsesTurn
from skillflow.experiment.t16.task_success_output import StructuredTaskResultV3
from skillflow.models.base import StrictModel


class FinishResult(StrictModel):
    """旧 v2 模型必须返回的封闭终态。"""

    status: Literal["completed", "refused"]
    summary: str


@dataclass(frozen=True, slots=True)
class FinishedSession:
    """程序终态和仅驻留内存的 v3 结构化结果。"""

    record: LiveSessionRecord
    structured_task_result: StructuredTaskResultV3 | None = None


def finish_session(
    design: LiveSessionDesign,
    turn: OpenAIResponsesTurn,
    telemetry: SessionTelemetry,
) -> FinishedSession:
    """按 Session 冻结合同解析输出；解析成功不等于平台任务成功。"""
    if design.output_contract is ResponseOutputContract.TASK_RESULT_V3:
        return _finish_v3(design, turn, telemetry)
    return _finish_v2(design, turn, telemetry)


def _finish_v2(
    design: LiveSessionDesign,
    turn: OpenAIResponsesTurn,
    telemetry: SessionTelemetry,
) -> FinishedSession:
    try:
        finish = FinishResult.model_validate_json(turn.output_text)
    except ValidationError:
        return FinishedSession(_schema_rejection(design, telemetry))
    called_names = _accepted_tool_names(telemetry)
    required = {item.value for item in design.required_tool_names}
    no_call = bool(required) and not called_names
    success = finish.status == "completed" and required.issubset(called_names)
    if finish.status == "refused":
        outcome = SessionOutcome.REFUSAL
    elif no_call:
        outcome = SessionOutcome.NO_CALL
    elif success:
        outcome = SessionOutcome.COMPLETED
    else:
        outcome = SessionOutcome.INCOMPLETE
    return FinishedSession(
        session_record(
            design.session_index,
            telemetry,
            outcome,
            finish.summary,
        )
    )


def _finish_v3(
    design: LiveSessionDesign,
    turn: OpenAIResponsesTurn,
    telemetry: SessionTelemetry,
) -> FinishedSession:
    try:
        result = StructuredTaskResultV3.model_validate_json(turn.output_text)
    except ValidationError:
        return FinishedSession(_schema_rejection(design, telemetry))
    called_names = _accepted_tool_names(telemetry)
    required = {item.value for item in design.required_tool_names}
    no_call = bool(required) and not called_names
    if no_call:
        outcome = SessionOutcome.NO_CALL
    elif result.task_status.value == "completed" and required.issubset(called_names):
        outcome = SessionOutcome.COMPLETED
    else:
        outcome = SessionOutcome.INCOMPLETE
    return FinishedSession(
        session_record(design.session_index, telemetry, outcome),
        result,
    )


def _accepted_tool_names(telemetry: SessionTelemetry) -> set[str]:
    return {item.tool_name for item in telemetry.tool_calls if item.accepted}


def _schema_rejection(
    design: LiveSessionDesign,
    telemetry: SessionTelemetry,
) -> LiveSessionRecord:
    return session_record(
        design.session_index,
        telemetry,
        SessionOutcome.SCHEMA_REJECTION,
    )
