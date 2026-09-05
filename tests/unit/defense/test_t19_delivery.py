import json
from pathlib import Path

import typer
from typer.testing import CliRunner

from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t19.campaign import CampaignPlan, CampaignSetup, run_campaign
from skillflow.experiment.t19.cli import app, register_t19_commands
from skillflow.experiment.t19.delivery import export_all
from skillflow.experiment.t19.freeze import prepare_phase
from skillflow.experiment.t19.matrix import precheck

ROOT = Path(__file__).resolve().parents[3]


def test_complete_cli_recompute_includes_source_integrity(tmp_path: Path) -> None:
    trial = next(t for t in precheck() if t.mechanism == "A1" and t.group == "Monitor")
    plan = CampaignPlan(
        domain="fake_reference",
        fixed=("T",),
        trials=(trial,),
        audit_aliases={trial.trial_id: ("authorization-claim",)},
    )
    phase, campaign, public = tmp_path / "phase", tmp_path / "campaign", tmp_path / "public"
    prepare_phase(ROOT, phase, plan, "delivery-test")
    run_campaign(CampaignSetup(ROOT, campaign, plan, V2FakeClient(), lambda _p: None))
    export_all(phase, campaign, tmp_path / "empty-live", public)
    runner = CliRunner()
    for label in ("one", "two"):
        result = runner.invoke(
            app, ["recompute", "--source", str(public), "--output", str(tmp_path / label)]
        )
        assert result.exit_code == 0, (result.output, result.exception)
        assert (
            json.loads((tmp_path / label / "integrity.json").read_text(encoding="utf-8"))["status"]
            == "passed"
        )
    checked = runner.invoke(
        app,
        [
            "check",
            "--left",
            str(tmp_path / "one"),
            "--right",
            str(tmp_path / "two"),
            "--output",
            str(tmp_path / "check.json"),
        ],
    )
    assert checked.exit_code == 0
    assert json.loads(checked.output)["detail_views_equal"]
    original = json.loads((tmp_path / "two/details.json").read_text(encoding="utf-8"))
    original["failure_event_counts"] = {"modified": 1}
    (tmp_path / "two/details.json").write_text(json.dumps(original), encoding="utf-8")
    mismatch = runner.invoke(
        app,
        [
            "check",
            "--left",
            str(tmp_path / "one"),
            "--right",
            str(tmp_path / "two"),
            "--output",
            str(tmp_path / "check-failed.json"),
        ],
    )
    assert mismatch.exit_code == 1


def test_register_is_offline_and_discloses_available_commands() -> None:
    parent = typer.Typer()
    register_t19_commands(parent)
    result = CliRunner().invoke(parent, ["t19", "--help"])
    assert result.exit_code == 0
    assert "recompute" in result.output
    assert "export" in result.output
