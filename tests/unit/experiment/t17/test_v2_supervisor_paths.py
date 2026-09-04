"""进程退出、暂停和非秘密控制的分支，不启动真实进程或请求。"""

from pathlib import Path
from unittest.mock import Mock

import pytest
from tests.unit.experiment.t17.v2_test_campaign_case import control_outcome, prepared_case

from skillflow.experiment.t17.v2 import campaign_setup, interruption, session_commands, supervisor
from skillflow.experiment.t17.v2 import supervisor_control as control
from skillflow.experiment.t17.v2.campaign_models import StageProgress
from skillflow.experiment.t17.v2.campaign_setup import PreparedCampaign
from skillflow.experiment.t17.v2.key_keeper import ChildExit, MemoryKeyKeeper
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t17.v2.session_models import (
    CommandReceipt,
    InterruptionManifest,
    ResumeCommand,
    SessionCommand,
    SessionCommandReceipt,
    SessionCommandRequestedError,
)
from skillflow.experiment.t17.v2.worker_models import StageJob, WorkerMessage


@pytest.fixture
def prepared(t17_cli_root: Path, request: pytest.FixtureRequest) -> PreparedCampaign:
    return prepared_case(t17_cli_root / request.node.name)


def test_inbox_retains_outcome_even_when_display_fails(prepared: PreparedCampaign) -> None:
    progress = StageProgress(
        stage=prepared.matrices[0].stage,
        scheduled_core=24,
        scheduled_replay=18,
        terminal_core=1,
        terminal_replay=0,
        failed_units=0,
        model_failures=0,
        usage=UnitUsage(),
    )
    observer = Mock(side_effect=OSError("display unavailable"))
    inbox = supervisor.WorkerInbox(observer)
    result = control_outcome(prepared, 0)
    for message in (
        WorkerMessage(kind="progress", progress=progress),
        WorkerMessage(kind="outcome", outcome=result),
        WorkerMessage(kind="error", reason="worker_error"),
    ):
        inbox.receive(message.model_dump_json().encode())
    assert inbox.outcomes == [result]
    assert inbox.errors == ["worker_error"]
    observer.assert_called_once_with(progress)


@pytest.mark.parametrize(
    "case",
    [
        (0, None, 1, None),
        (1, None, 1, "worker_exit"),
        (0, "pipe_error", 1, "pipe_error"),
        (0, None, 0, "worker_exit"),
        (0, None, 2, "worker_exit"),
        (0, None, -1, "worker_reported_error"),
    ],
)
def test_worker_needs_one_clean_outcome(
    prepared: PreparedCampaign,
    case: tuple[int, str | None, int, str | None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, reason, messages, expected_reason = case
    job = StageJob(prepared=prepared, index=0, attempt_number=1, approved_phase=prepared.phases[0])
    passed, failed = control_outcome(prepared, 0), control_outcome(prepared, 0, passed=False)
    keeper = Mock(spec=MemoryKeyKeeper)

    def execute(payload: bytes, worker: object, callback: object) -> ChildExit:
        assert StageJob.model_validate_json(payload) == job
        if messages == -1:
            callback(
                WorkerMessage(kind="error", reason="worker_reported_error")
                .model_dump_json()
                .encode()
            )
        for _ in range(max(messages, 0)):
            callback(WorkerMessage(kind="outcome", outcome=passed).model_dump_json().encode())
        return ChildExit(exit_code, reason)

    keeper.execute.side_effect = execute
    fallback = Mock(return_value=failed)
    monkeypatch.setattr(supervisor, "interrupted_outcome", fallback)
    result = supervisor.run_stage_process(job, keeper, Mock())
    if expected_reason is None:
        assert result == passed
        fallback.assert_not_called()
    else:
        assert result == failed
        fallback.assert_called_once_with(job, expected_reason)


@pytest.mark.parametrize("resume", [False, True])
def test_supervisor_retains_failure_before_optional_new_attempt(
    prepared: PreparedCampaign, resume: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        campaign_setup, "claim_path", lambda _: prepared.setup.output.parent / "claim"
    )
    jobs = []

    def execute(job: StageJob, keeper: object, observer: object) -> object:
        jobs.append(job)
        return control_outcome(prepared, job.index, passed=len(jobs) > 1).model_copy(
            update={
                "attempt_number": job.attempt_number,
                "raw_relative_path": (
                    prepared.setup.output
                    / prepared.matrices[job.index].stage.value
                    / f"attempt-{job.attempt_number:02d}/raw"
                )
                .relative_to(prepared.setup.root)
                .as_posix(),
            }
        )

    monkeypatch.setattr(supervisor, "run_stage_process", execute)
    permission = Mock(return_value=resume)
    monkeypatch.setattr(supervisor, "await_resume", permission)
    result = supervisor.run_supervised(prepared, Mock(), Mock(), Mock())
    assert len(result.failed_attempts) == 1
    assert result.all_stages_finished is resume
    assert len(jobs) == (6 if resume else 1)
    if resume:
        assert jobs[1].index == 0
        assert jobs[1].attempt_number == 2
        assert jobs[1].failed == result.failed_attempts
        assert len(result.stages) == 5
        assert result.stages[0].raw_relative_path != result.failed_attempts[0].raw_relative_path
    permission.assert_called_once()
    assert (prepared.setup.output / "campaign-result.json").is_file()


@pytest.mark.parametrize("action", ["stop_keep_evidence", "retry_interrupted_stage"])
def test_resume_preserves_invalid_commands_and_consumes_valid_one_once(
    prepared: PreparedCampaign,
    action: str,
) -> None:
    directory = prepared.setup.output
    commands = directory / "control"
    commands.mkdir(parents=True)
    outcome = control_outcome(prepared, 0, passed=False)
    (commands / "command-00.json").write_text("invalid", encoding="utf-8")
    (commands / "receipt-command-00.json").write_text("already-consumed", encoding="utf-8")
    (commands / "command-01.json").write_text("invalid", encoding="utf-8")
    valid = ResumeCommand(
        command_id="valid", action=action, raw_relative_path=outcome.raw_relative_path
    )
    (commands / "command-02.json").write_text(valid.model_dump_json(), encoding="utf-8")
    assert control.await_resume(directory, outcome, Mock()) is (action == "retry_interrupted_stage")
    rejected = CommandReceipt.model_validate_json(
        (commands / "receipt-command-01.json").read_text(encoding="utf-8")
    )
    accepted = CommandReceipt.model_validate_json(
        (commands / "receipt-command-02.json").read_text(encoding="utf-8")
    )
    assert not rejected.accepted
    assert accepted.accepted
    assert len(list(commands.glob("command-*.json"))) == 3


def test_resume_survives_control_errors_without_requesting_a_key(
    prepared: PreparedCampaign,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared.setup.output.mkdir()
    command = SessionCommand(command_id="stop", action="stop_keep_evidence")
    monkeypatch.setattr(
        control,
        "read_session_command",
        Mock(side_effect=[KeyboardInterrupt(), OSError(), None, command]),
    )
    sleeper, notice = Mock(), Mock()
    monkeypatch.setattr(control.time, "sleep", sleeper)
    with pytest.raises(SessionCommandRequestedError) as caught:
        control.await_resume(
            prepared.setup.output,
            control_outcome(prepared, 0, passed=False),
            notice,
            prepared.setup.output,
        )
    assert caught.value.command == command
    assert notice.call_count == 2
    assert [call.args[0] for call in sleeper.call_args_list] == [1, 0.5]


def test_session_command_receipts_do_not_grant_api_authorization(t17_cli_root: Path) -> None:
    directory = t17_cli_root / "session-controls"
    directory.mkdir()
    (directory / "session-command-01.json").write_text("invalid", encoding="utf-8")
    command = SessionCommand(command_id="stop", action="stop_keep_evidence")
    (directory / "session-command-02.json").write_text(command.model_dump_json(), encoding="utf-8")
    assert session_commands.read_session_command(directory) == command
    assert session_commands.read_session_command(directory) is None
    for filename, valid in (("01", False), ("02", True)):
        receipt = SessionCommandReceipt.model_validate_json(
            (directory / f"receipt-session-command-{filename}.json").read_text(encoding="utf-8")
        )
        assert receipt.schema_valid is valid
        assert not receipt.grants_api_authorization
        assert (directory / f"session-command-{filename}.json").is_file()


def test_session_wait_only_retries_control_reads(
    t17_cli_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command = SessionCommand(command_id="stop", action="stop_keep_evidence")
    monkeypatch.setattr(
        session_commands,
        "read_session_command",
        Mock(side_effect=[OSError(), KeyboardInterrupt(), None, command]),
    )
    sleeper, notice = Mock(), Mock()
    monkeypatch.setattr(session_commands.time, "sleep", sleeper)
    assert session_commands.await_session_command(t17_cli_root, notice) == command
    assert notice.call_count == 2
    assert [call.args[0] for call in sleeper.call_args_list] == [1, 1, 0.5]


@pytest.mark.parametrize("has_manifest", [False, True])
def test_interruption_writes_new_terminal_evidence_without_overwriting_raw(
    prepared: PreparedCampaign,
    has_manifest: bool,
) -> None:
    raw = prepared.setup.output / "canary/attempt-01/raw"
    raw.mkdir(parents=True)
    marker = raw / "preserved.txt"
    marker.write_text("original-evidence", encoding="utf-8")
    if has_manifest:
        (raw / "raw-manifest.json").write_text("{}", encoding="utf-8")
    job = StageJob(prepared=prepared, index=0, attempt_number=1, approved_phase=prepared.phases[0])
    result = interruption.interrupted_outcome(job, "worker_exit")
    assert result.status == "failed"
    assert result.reason == "worker_exit"
    assert (result.raw_manifest is not None) is has_manifest
    manifest = InterruptionManifest.model_validate_json(
        (raw.parent / "recovery/interruption-manifest.json").read_text(encoding="utf-8")
    )
    assert not manifest.stage_passed
    assert len(manifest.interrupted_terminals) == 42
    assert marker.read_text(encoding="utf-8") == "original-evidence"
