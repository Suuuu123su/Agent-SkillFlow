"""空目标仅凭实际零字节事实判为不适用，不重新调用模型。"""

from pathlib import Path

import pytest

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.reference_backend import ReferenceModelDecision, ReferenceModelRequest
from skillflow.experiment.t17.v2.binding import validate_replay_binding
from skillflow.experiment.t17.v2.config_models import V2Configuration
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.replay_execution import execute_replay
from skillflow.experiment.t17.v2.runtime_models import ModelOutcomeError
from skillflow.experiment.t17.v2.stage_contract import freeze_phase
from skillflow.experiment.t17.v2.unit_execution import ExecutionContext, execute_core


class EmptyResponseClient:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        self.calls += 1
        if self.calls == 1:
            raise ModelOutcomeError("schema_rejection")
        return ReferenceModelDecision(selected_action_ids=(), output_text="")


def test_empty_target_keeps_failure_and_uses_no_replay_call(tmp_path: Path) -> None:
    root = Path.cwd()
    config = read_model(root / "experiments/t17/v2/preregistration.json", V2Configuration)
    matrix = build_matrix(root, config, T17LiveStage.MODEL2_CANARY)
    phase = freeze_phase(root, config, matrix, "fake_reference")
    client = EmptyResponseClient()
    context = ExecutionContext(root, tmp_path / "empty-target", config, matrix, phase, client)
    trial = matrix.trials[0]
    execution = execute_core(context, trial)
    assert execution.terminal.decisions[0].behavior == "schema_rejection"
    calls = client.calls
    replay = execute_replay(context, trial, execution, next(iter(trial.replay_pair_ids)))
    assert replay.status == "not_applicable"
    assert replay.reason == "target_empty_no_neutral_form"
    assert replay.absent_source == execution.terminal.data.facts
    assert client.calls == calls
    validate_replay_binding(execution.terminal, replay)
    with pytest.raises(ValueError, match="v2_replay_false_absence"):
        validate_replay_binding(
            execution.terminal,
            replay.model_copy(
                update={
                    "reason": "target_not_produced",
                }
            ),
        )
    target = execution.terminal.data.artifact_ids_by_alias[replay.target_alias]
    facts = replay.absent_source
    nonempty = facts.model_copy(
        update={
            "artifacts": tuple(
                a.model_copy(update={"content_length": 1}) if a.artifact_id == target else a
                for a in facts.artifacts
            )
        }
    )
    altered_core = execution.terminal.model_copy(
        update={"data": execution.terminal.data.model_copy(update={"facts": nonempty})}
    )
    with pytest.raises(ValueError, match="v2_replay_false_absence"):
        validate_replay_binding(altered_core, replay.model_copy(update={"absent_source": nonempty}))
