from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillflow.cli import app
from skillflow.experiment.t17.minimal.report_models import MinimalMeasurement
from skillflow.experiment.t17.minimal.run_models import MinimalExecutionStatus
from skillflow.experiment.t17.minimal.schema_models import (
    minimal_schema_documents,
    schema_filename,
    static_model_validator,
    write_minimal_schemas,
)


def test_minimal_static_schemas_cover_raw_and_reports() -> None:
    names = {name for name, _ in minimal_schema_documents()}
    assert {
        "t17-minimal-domain-report.schema.json",
        "t17-minimal-configuration.schema.json",
        "t17-minimal-observed-trace.schema.json",
        "t17-minimal-oracle-trace.schema.json",
        "t17-minimal-replay-pair.schema.json",
        "t17-minimal-execution-status.schema.json",
    } <= names


def test_cli_freeze_is_zero_api_and_non_overwriting(t17_cli_root: Path) -> None:
    runner = CliRunner()
    args = ["t17", "minimal", "freeze", "--output", str(t17_cli_root / "frozen")]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "API=0" in result.output
    assert (t17_cli_root / "frozen" / "preregistration.yaml").is_file()
    assert runner.invoke(app, args).exit_code == 2


def test_partial_status_cannot_claim_completed() -> None:
    document = {
        "domain": "scripted",
        "phase_contract_sha256": "a" * 64,
        "observed_core_runs": 1,
        "observed_replay_pairs": 0,
        "status": "incomplete",
        "reason": "run_did_not_complete",
    }
    assert MinimalExecutionStatus.model_validate(document).actual_api_calls == 0
    with pytest.raises(ValueError, match=r"status|complete"):
        MinimalExecutionStatus.model_validate({**document, "status": "measured", "reason": None})


def test_schema_generation_never_overwrites_and_drift_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "schemas"
    write_minimal_schemas(destination)
    with pytest.raises(ValueError, match="already_exists"):
        write_minimal_schemas(destination)
    monkeypatch.chdir(tmp_path)
    static_model_validator(MinimalMeasurement)
    (destination / schema_filename("measurement")).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="static_schema_drift"):
        static_model_validator(MinimalMeasurement)


def test_cli_rejects_output_outside_project_without_writes() -> None:
    forbidden = Path.cwd().parent / "t17-forbidden-output"
    result = CliRunner().invoke(app, ["t17", "minimal", "freeze", "--output", str(forbidden)])
    assert result.exit_code == 2
    assert not forbidden.exists()


def test_cli_fixture_is_project_local(t17_cli_root: Path) -> None:
    assert t17_cli_root.is_dir()
    assert t17_cli_root.parent == Path.cwd() / ".tmp"
