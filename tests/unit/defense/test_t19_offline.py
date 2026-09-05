import json
from pathlib import Path

from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t19.campaign import CampaignPlan, CampaignSetup, run_campaign
from skillflow.experiment.t19.formal_plan import formal_plan
from skillflow.experiment.t19.freeze import prepare_phase, verify_phase
from skillflow.experiment.t19.matrix import precheck
from skillflow.experiment.t19.offline import check, export, recompute

ROOT = Path(__file__).resolve().parents[3]


def test_offline_export_freeze_and_fact_recompute(tmp_path: Path) -> None:
    trials = tuple(t for t in precheck() if t.mechanism == "A1")
    plan = CampaignPlan(
        domain="fake_reference",
        fixed=("T",),
        trials=trials,
        audit_aliases={t.trial_id: ("authorization-claim",) for t in trials},
    )
    phase = tmp_path / "phase"
    frozen = prepare_phase(ROOT, phase, plan, "offline-test")
    assert verify_phase(ROOT, phase)[0] == frozen
    campaign = tmp_path / "campaign"
    run_campaign(CampaignSetup(ROOT, campaign, plan, V2FakeClient(), lambda _p: None))
    export(phase, campaign, tmp_path / "empty-live", tmp_path / "public")
    first = recompute(tmp_path / "public", tmp_path / "report-one")
    second = recompute(tmp_path / "public", tmp_path / "report-two")
    assert first == second
    assert first.data_status == "complete"
    assert check(tmp_path / "report-one", tmp_path / "report-two")["status"] == "passed"
    raw = json.loads((tmp_path / "report-two/metrics.json").read_text(encoding="utf-8"))
    raw["completed_core"] += 1
    (tmp_path / "report-two/metrics.json").write_text(json.dumps(raw), encoding="utf-8")
    assert check(tmp_path / "report-one", tmp_path / "report-two")["status"] == "failed"


def test_formal_audits_are_mechanically_complete_and_balanced() -> None:
    plan = formal_plan()
    assert len(plan.trials) == 336
    assert sum(len(v) for v in plan.audit_aliases.values()) == 168
    for group in ("Monitor", "Grant-only", "Best Fixed", "All", "Evidence", "Coarse"):
        selected = tuple(t for t in plan.trials if t.group == group)
        assert len(selected) == 56
        assert sum(len(plan.audit_aliases.get(t.trial_id, ())) for t in selected) == 28
