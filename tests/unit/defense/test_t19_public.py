import json
from pathlib import Path

import pytest

from skillflow.experiment.t17.v2.canonical import canonical_digest
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t19.campaign import CampaignPlan, CampaignSetup, run_campaign
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.experiment.t19.matrix import precheck
from skillflow.experiment.t19.metric_adapter import bind_skill
from skillflow.experiment.t19.public_facts import PublicCore, PublicReplay
from skillflow.experiment.t19.replay import ReplayRecord
from skillflow.experiment.t19.reporting import PublicIndex, report
from skillflow.experiment.t19.tasks import task_variant

ROOT = Path(__file__).resolve().parents[3]


def test_fact_only_report_rebuilds_and_does_not_hide_missing_audit(tmp_path: Path) -> None:
    trials = tuple(t for t in precheck() if t.mechanism == "A1")
    plan = CampaignPlan(
        domain="fake_reference",
        fixed=("T",),
        trials=trials,
        audit_aliases={t.trial_id: ("authorization-claim",) for t in trials},
    )
    run_campaign(CampaignSetup(ROOT, tmp_path, plan, V2FakeClient(), lambda _p: None))
    public = []
    for trial in trials:
        core = CoreRecord.model_validate_json(
            (tmp_path / "core" / (trial.trial_id + ".json")).read_text(encoding="utf-8")
        )
        row = PublicCore.capture(
            trial, bind_skill(task_variant(ROOT, trial.mechanism, trial.role, trial.template)), core
        )
        assert "proof" not in json.loads(row.model_dump_json())["inputs"]
        assert row.rebuild() == core
        public.append(row)
    pairs = tuple(
        PublicReplay.capture(ReplayRecord.model_validate_json(p.read_text(encoding="utf-8")))
        for p in sorted((tmp_path / "audits").glob("*/*.json"))
    )
    index = PublicIndex(phase_sha256=canonical_digest("test"), plan=plan)
    result = report(index, tuple(public), pairs)
    assert result.data_status == "complete"
    assert result.metrics["Monitor/A1/alr"].value == 1
    assert (
        result.metrics["main/Evidence/receipt_coverage"].value is None
        or result.metrics["main/Evidence/receipt_coverage"].value == 1
    )
    incomplete = report(index, tuple(public), pairs[:-1])
    assert incomplete.data_status == "incomplete"
    assert incomplete.metrics["Monitor/A1/alr"].value is None
    assert incomplete.metrics["audit/terminal_coverage"].value == 0.75
    tampered = public[0].model_copy(update={"runtime": {**public[0].runtime, "proof": {}}})
    with pytest.raises(ValueError, match="public_runtime_fields"):
        tampered.rebuild()
