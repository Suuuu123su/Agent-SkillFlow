import pytest

from skillflow.pilot.errors import (
    OpenClawEventFileError,
    OpenClawPilotError,
    PilotComparisonError,
    PilotPlanError,
    PilotRunError,
)


@pytest.mark.parametrize(
    "error",
    [
        PilotComparisonError.scenario_mismatch(),
        PilotPlanError.fixture_missing("skill-a"),
        PilotPlanError.shell_forbidden(),
        PilotPlanError.unsupported_asset("memory:/wrong"),
        PilotPlanError.unsupported_file("fixture://wrong"),
        PilotPlanError.unsafe_path("../escape"),
        PilotPlanError.marker_missing(),
        PilotPlanError.source_asset_count(),
        OpenClawEventFileError.blank_line(2),
        OpenClawEventFileError.invalid_line(3, "bad json"),
        OpenClawEventFileError.sequence_invalid(),
        OpenClawEventFileError.effect_incomplete(),
        OpenClawPilotError.driver_failed(2, "failed"),
        OpenClawPilotError.target_evidence_incomplete(),
        OpenClawPilotError.request_exists("request.json"),
        PilotRunError.output_exists("evidence"),
        PilotRunError.git_failed("missing checkout"),
        PilotRunError.commit_mismatch("actual", "expected"),
        PilotRunError.executable_missing("node"),
    ],
)
def test_boundary_errors_have_stable_nonempty_diagnostics(error: Exception) -> None:
    assert str(error).strip()
