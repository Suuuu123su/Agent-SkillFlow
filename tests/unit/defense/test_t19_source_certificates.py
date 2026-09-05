from pathlib import Path

import pytest

from skillflow.experiment.t19.campaign import CampaignPlan, CampaignSetup, run_campaign
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.experiment.t19.matrix import precheck
from skillflow.experiment.t19.metric_adapter import bind_skill
from skillflow.experiment.t19.public_facts import PublicCore, PublicReplay
from skillflow.experiment.t19.replay import ReplayRecord
from skillflow.experiment.t19.source_certificates import (
    SourceCertificates,
    collect,
    validate_sources,
)
from skillflow.experiment.t19.tasks import task_variant

from .test_t19_tasks import EmptyFailureClient, ScalarSourceClient

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("mechanism", ["M2", "A1"])
def test_inapplicability_is_bound_to_actual_source_and_not_a_zero(
    tmp_path: Path, mechanism: str
) -> None:
    trial = next(t for t in precheck() if t.mechanism == mechanism and t.group == "Monitor")
    aliases = ("authorization-claim",) if mechanism == "A1" else ("m2-memory-1", "m2-memory-3")
    plan = CampaignPlan(
        domain="fake_reference", fixed=(), trials=(trial,), audit_aliases={trial.trial_id: aliases}
    )
    run_campaign(
        CampaignSetup(
            ROOT,
            tmp_path,
            plan,
            ScalarSourceClient() if mechanism == "A1" else EmptyFailureClient(),
            lambda _p: None,
        )
    )
    core = CoreRecord.model_validate_json(
        (tmp_path / "core" / (trial.trial_id + ".json")).read_text(encoding="utf-8")
    )
    public = PublicCore.capture(
        trial, bind_skill(task_variant(ROOT, mechanism, "attack", "development")), core
    )
    pairs = tuple(
        PublicReplay.capture(ReplayRecord.model_validate_json(p.read_text(encoding="utf-8")))
        for p in sorted((tmp_path / "audits").glob("*/*.json"))
    )
    certificates = collect(tmp_path, pairs)
    assert validate_sources((public,), pairs, certificates) == ()
    assert all(not c.separable for c in certificates.items)
    assert all(c.produced == (mechanism == "A1") for c in certificates.items)
    assert all(p.rebuild().proof is None for p in pairs)
    first = certificates.items[0].model_copy(update={"source_prefix_steps": 100})
    tampered = SourceCertificates(items=(first, *certificates.items[1:]))
    assert any("prefix_step_mismatch" in s for s in validate_sources((public,), pairs, tampered))
    assert validate_sources((public,), pairs, SourceCertificates(items=()))
