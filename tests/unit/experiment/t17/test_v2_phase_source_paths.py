"""断点续跑只接受已经批准的第二模型修订，不接受任务或提示漂移。"""

from pathlib import Path

import pytest
from tests.unit.experiment.t17.v2_test_campaign_case import control_gate, prepared_case

from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.frozen import FrozenFile
from skillflow.experiment.t17.v2.phase_sources import phase_index
from skillflow.experiment.t17.v2.run_models import StageResult


@pytest.mark.parametrize(
    "case",
    [
        "no_source",
        "allowed_canary",
        "allowed_model2",
        "wrong_stage",
        "changed_contract",
        "unapproved_code",
        "canary_live_client",
        "duplicate",
    ],
)
def test_source_phase_accepts_only_approved_changes(t17_cli_root: Path, case: str) -> None:
    prepared = prepared_case(t17_cli_root / case)
    index = 0 if case == "wrong_stage" else (3 if case == "allowed_model2" else 2)
    phase = prepared.phases[index]
    changed = dict(phase.runtime_files)
    name = "src/skillflow/experiment/t17/v2/"
    name += (
        "live_client.py"
        if case in {"allowed_model2", "canary_live_client"}
        else "replay_execution.py"
    )
    if case == "unapproved_code":
        name = "src/skillflow/experiment/t17/v2/prompt_contract.py"
    changed[name] = FrozenFile(sha256="b" * 64, size_bytes=7)
    source = phase.model_copy(update={"runtime_files": changed})
    if case == "changed_contract":
        source = source.model_copy(update={"protocol_id": "changed-task-contract"})
    if case == "duplicate":
        source = phase
    result = StageResult(
        phase=phase,
        source_phases=() if case == "no_source" else (source,),
        cores=(),
        replays=(),
        gate=control_gate(prepared, index),
    )
    errors = {
        "wrong_stage": "source_phase_contract_mismatch",
        "changed_contract": "source_phase_contract_mismatch",
        "unapproved_code": "source_phase_runtime_change_not_approved",
        "canary_live_client": "source_phase_runtime_change_not_approved",
        "duplicate": "duplicate_source_phase",
    }
    if case in errors:
        with pytest.raises(ValueError, match=errors[case]):
            phase_index(result)
    else:
        phases = phase_index(result)
        assert phases[model_digest(phase)] == phase
        assert len(phases) == (1 if case == "no_source" else 2)
