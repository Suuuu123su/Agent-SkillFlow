"""恢复指令只能绑定失败尝试，不能重新采样模型或跳过阶段门。"""

import pytest

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t17.v2.supervisor_control import ResumeCommand, validate_resume


def test_resume_only_allows_the_same_interrupted_stage() -> None:
    outcome = StageOutcome(
        stage=T17LiveStage.CANARY,
        status="failed",
        reason="worker_exit",
        raw_relative_path="runs/new/canary/attempt-01/raw",
        usage=UnitUsage(),
    )
    command = ResumeCommand(
        command_id="resume-1",
        action="retry_interrupted_stage",
        raw_relative_path=outcome.raw_relative_path,
    )
    validate_resume(command, outcome)
    with pytest.raises(ValueError, match="v2_resume_attempt_binding"):
        validate_resume(command.model_copy(update={"raw_relative_path": "different"}), outcome)
    with pytest.raises(ValueError, match="v2_resume_not_infrastructure_interruption"):
        validate_resume(command, outcome.model_copy(update={"reason": "phase_gate_failed"}))


def test_stop_never_authorizes_more_requests() -> None:
    outcome = StageOutcome(
        stage=T17LiveStage.CANARY,
        status="failed",
        reason="phase_gate_failed",
        raw_relative_path="runs/new/canary/attempt-01/raw",
        usage=UnitUsage(),
    )
    command = ResumeCommand(
        command_id="stop-1",
        action="stop_keep_evidence",
        raw_relative_path=outcome.raw_relative_path,
    )
    validate_resume(command, outcome)
