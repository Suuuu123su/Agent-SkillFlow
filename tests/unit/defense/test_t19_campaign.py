from pathlib import Path

import pytest

from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t19.campaign import CampaignPlan, CampaignSetup, Progress, run_campaign
from skillflow.experiment.t19.matrix import precheck

ROOT = Path(__file__).resolve().parents[3]


def test_campaign_persists_sources_and_resumes_without_model_calls(tmp_path: Path) -> None:
    trials = tuple(t for t in precheck() if t.group == "Monitor" and t.mechanism in {"M2", "A1"})
    plan = CampaignPlan(
        domain="fake_reference",
        fixed=("T",),
        trials=trials,
        audit_aliases={
            t.trial_id: ("authorization-claim",)
            if t.mechanism == "A1"
            else ("m2-memory-1", "m2-memory-3")
            for t in trials
        },
    )
    progress: list[Progress] = []
    client = V2FakeClient()
    setup = CampaignSetup(ROOT, tmp_path, plan, client, progress.append)
    run_campaign(setup)
    assert progress[-1].completed_core == 2
    assert progress[-1].completed_audit == 3
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    run_campaign(setup)
    assert all(p.read_bytes() == value for p, value in before.items())
    assert len(tuple((tmp_path / "core").glob("*.json"))) == 2
    changed = plan.model_copy(update={"fixed": ("P",)})
    with pytest.raises(ValueError, match="resume_plan_drift"):
        run_campaign(CampaignSetup(ROOT, tmp_path, changed, client, progress.append))


def test_unclosed_core_is_not_silently_resampled(tmp_path: Path) -> None:
    trial = precheck()[0]
    (tmp_path / "raw" / trial.trial_id).mkdir(parents=True)
    plan = CampaignPlan(domain="fake_reference", fixed=("T",), trials=(trial,), audit_aliases={})
    with pytest.raises(ValueError, match="unclosed_core"):
        run_campaign(CampaignSetup(ROOT, tmp_path, plan, V2FakeClient(), lambda _: None))
