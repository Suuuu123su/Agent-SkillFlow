from dataclasses import replace
from pathlib import Path

from skillflow.experiment.t16.openai_response_models import OpenAIResponsesCall
from skillflow.experiment.t16.openai_responses import OpenAIResponsesTurn
from skillflow.experiment.t16.task_success_live_mock import TaskSuccessMockLiveClient
from skillflow.experiment.t16.task_success_live_preflight import (
    T16D2Environment,
    load_t16d2_environment,
)
from skillflow.experiment.t16.task_success_live_report_models import T16D2BridgeReport
from skillflow.experiment.t16.task_success_live_run import (
    T16D2RunRequest,
    T16D2StopReason,
    execute_t16d2_run,
    load_t16d2_raw_records,
)

ROOT = Path(__file__).parents[4]


def _environment() -> T16D2Environment:
    return load_t16d2_environment(
        {
            "SKILLFLOW_PROVIDER": "openai",
            "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
            "SKILLFLOW_MAX_USD": "3",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )


def test_mock_runner_applies_canary_gate_then_saves_48_immutable_records(
    tmp_path: Path,
) -> None:
    output = tmp_path / "attempt-01"

    summary = execute_t16d2_run(
        T16D2RunRequest(ROOT, output, _environment()),
        TaskSuccessMockLiveClient(),
    )

    records = load_t16d2_raw_records(output / "raw-trials.jsonl")
    assert summary.scheduled == 48
    assert summary.observed == 48
    assert summary.canary_observed == 11
    assert summary.canary_gate_passed is True
    assert summary.final_gate_passed is True
    assert summary.stop_reason is None
    assert len(records) == 48
    assert len({item.live_trial.result.trial_id for item in records}) == 48
    assert (output / "stage-gate-canary.json").is_file()
    assert (output / "stage-gate-final.json").is_file()
    assert (output / "checkpoint-011.json").is_file()
    assert (output / "checkpoint-023.json").is_file()
    assert (output / "checkpoint-035.json").is_file()
    assert (output / "checkpoint-047.json").is_file()
    assert (output / "checkpoint-048.json").is_file()
    report = T16D2BridgeReport.model_validate_json(
        (output / "bridge-report.json").read_text(encoding="utf-8")
    )
    assert len(report.condition_reports) == 12
    assert sum(report.joint_outcomes.model_dump().values()) == 48
    assert set(report.formal_metrics.values()) == {"N/A"}


class RevisionDriftClient(TaskSuccessMockLiveClient):
    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        turn = super().create(call)
        if self.call_ordinal >= 4:
            return replace(turn, model_revision="gpt-5.6-luna-drift")
        return turn


def test_runner_stops_after_saving_first_model_revision_drift(tmp_path: Path) -> None:
    output = tmp_path / "drift-attempt"

    summary = execute_t16d2_run(
        T16D2RunRequest(ROOT, output, _environment()),
        RevisionDriftClient(),
    )

    assert summary.observed == 2
    assert summary.stop_reason is T16D2StopReason.MODEL_REVISION_CHANGED
    assert len(load_t16d2_raw_records(output / "raw-trials.jsonl")) == 2
