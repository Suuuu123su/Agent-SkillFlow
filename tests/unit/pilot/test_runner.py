import subprocess
from pathlib import Path

import pytest

from skillflow.models.metrics import MetricStatus, RatioMetric
from skillflow.pilot.errors import PilotRunError
from skillflow.pilot.models import PilotScenarioComparison, ProvenanceBasis
from skillflow.pilot.runner import (
    OPENCLAW_COMMIT,
    PILOT_SCENARIOS,
    PilotRunRequest,
    execute_t15_pilot,
    openclaw_revision,
    require_pinned_commit,
)


def test_runner_uses_the_three_preregistered_t15_scenarios() -> None:
    assert tuple(path.as_posix() for path in PILOT_SCENARIOS) == (
        "scenarios/benign/b0_legal_summary.yaml",
        "scenarios/benign/g0_legal_cross_skill.yaml",
        "scenarios/attacks/m2_revoked_memory_residual.yaml",
    )


def test_openclaw_revision_must_equal_the_audited_commit() -> None:
    require_pinned_commit(OPENCLAW_COMMIT)

    with pytest.raises(PilotRunError, match="revision 不匹配"):
        require_pinned_commit("0" * 40)


def test_openclaw_revision_uses_git_argument_array(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def completed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=f"{OPENCLAW_COMMIT}\n", stderr=""
        )

    monkeypatch.setattr("skillflow.pilot.runner.subprocess.run", completed)

    assert openclaw_revision(tmp_path, Path("git")) == OPENCLAW_COMMIT
    assert captured["args"][0] == ("git", "rev-parse", "HEAD")
    assert captured["kwargs"]["cwd"] == tmp_path


@pytest.mark.parametrize("failure", ["returncode", "oserror"])
def test_openclaw_revision_failures_are_structured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    if failure == "returncode":

        def replacement(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="not a checkout"
            )
    else:

        def replacement(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise OSError

    monkeypatch.setattr("skillflow.pilot.runner.subprocess.run", replacement)

    with pytest.raises(PilotRunError, match="无法读取 OpenClaw revision"):
        openclaw_revision(tmp_path, Path("git"))


def _comparison(scenario_id: str) -> PilotScenarioComparison:
    missing = RatioMetric(
        numerator=0,
        denominator=0,
        value=None,
        status=MetricStatus.NOT_APPLICABLE,
    )
    return PilotScenarioComparison(
        scenario_id=scenario_id,
        mock_effect_count=0,
        openclaw_effect_count=0,
        effect_count_match=True,
        mock_provenance_recall=missing,
        openclaw_provenance_recall=missing,
        mock_provenance_basis=ProvenanceBasis.GRAPH_WIDE_ARTIFACTS,
        openclaw_provenance_basis=ProvenanceBasis.TARGET_EFFECT_LABELS,
        provenance_basis_match=False,
        provenance_delta=None,
        policy_match=False,
        differences=("grant_matcher",),
    )


def test_execute_t15_pilot_runs_three_pairs_and_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair_paths: list[Path] = []

    def pinned(root: Path, git: Path) -> str:
        return OPENCLAW_COMMIT

    monkeypatch.setattr("skillflow.pilot.runner.openclaw_revision", pinned)

    def pair(
        scenario: Path,
        output: Path,
        mock: object,
        openclaw: object,
    ) -> PilotScenarioComparison:
        pair_paths.append(scenario)
        output.mkdir(parents=True)
        return _comparison(scenario.stem)

    monkeypatch.setattr("skillflow.pilot.runner.run_pilot_pair", pair)
    output = tmp_path / "pilot"
    request = PilotRunRequest(
        project_root=Path.cwd(),
        openclaw_root=tmp_path / "openclaw",
        output_root=output,
        node_path=Path("node"),
        git_path=Path("git"),
    )

    report = execute_t15_pilot(request)

    assert len(report.comparisons) == 3
    assert pair_paths == [Path.cwd() / item for item in PILOT_SCENARIOS]
    assert report.real_credentials_used is False
    assert report.external_effects_replaced is True
    assert report.production_state_modified is False
    assert (output / "pilot-report.json").is_file()


def test_execute_t15_pilot_rejects_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    request = PilotRunRequest(
        project_root=tmp_path,
        openclaw_root=tmp_path,
        output_root=output,
        node_path=Path("node"),
        git_path=Path("git"),
    )

    with pytest.raises(PilotRunError, match="拒绝覆盖"):
        execute_t15_pilot(request)
