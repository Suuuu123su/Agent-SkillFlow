from pathlib import Path

from skillflow.experiment.t16.live_tools import LiveToolName
from skillflow.experiment.t16.openai_output_schemas import ResponseOutputContract
from skillflow.experiment.t16.task_success_live_design import (
    TaskSuccessLiveTrialDesign,
    build_task_success_live_design,
)
from skillflow.experiment.t16.task_success_live_preflight import load_t16d2_inputs

ROOT = Path(__file__).parents[4]


def _design(condition_id: str) -> TaskSuccessLiveTrialDesign:
    inputs = load_t16d2_inputs(ROOT)
    trial = next(
        item
        for item in inputs.matrix.trials
        if item.condition_id == condition_id
        and item.repeat_index == 1
        and item.semantic_instance_id.endswith("v01")
    )
    return build_task_success_live_design(inputs, trial)


def test_b0_v3_adds_safe_sink_receipt_and_structured_terminal_result() -> None:
    design = _design("b0")

    assert design.task_success_spec_id == "ts-b0-v3"
    assert design.task_output_contract_id == "report-summary-v3"
    assert design.safe_effect_payload == b"safe-fixture:b0-report-read:v3"
    assert design.sessions[0].tool_names == (
        LiveToolName.READ_ASSET,
        LiveToolName.SAFE_EFFECT,
    )
    assert design.sessions[0].required_tool_names == design.sessions[0].tool_names
    assert design.sessions[0].output_contract is ResponseOutputContract.TASK_RESULT_V3


def test_g0_v3_uses_two_sessions_and_only_final_session_returns_task_result() -> None:
    design = _design("g0")

    assert tuple(item.session_index for item in design.sessions) == (0, 1)
    assert design.sessions[0].required_tool_names == (
        LiveToolName.READ_ASSET,
        LiveToolName.WRITE_MEMORY,
    )
    assert design.sessions[1].required_tool_names == (
        LiveToolName.READ_MEMORY,
        LiveToolName.SAFE_EFFECT,
    )
    assert design.sessions[0].output_contract is ResponseOutputContract.FINISH_V2
    assert design.sessions[1].output_contract is ResponseOutputContract.TASK_RESULT_V3


def test_m2_v3_preserves_four_sessions_and_only_session_three_returns_task_result() -> None:
    design = _design("m2-target")

    assert tuple(item.session_index for item in design.sessions) == (0, 1, 2, 3)
    assert tuple(item.output_contract for item in design.sessions) == (
        ResponseOutputContract.FINISH_V2,
        ResponseOutputContract.FINISH_V2,
        ResponseOutputContract.FINISH_V2,
        ResponseOutputContract.TASK_RESULT_V3,
    )
