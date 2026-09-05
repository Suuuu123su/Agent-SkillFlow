from pathlib import Path

from skillflow.experiment.t17.v2.canonical import canonical_digest
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t19.execution import ExecutionSetup, execute
from skillflow.experiment.t19.matrix import precheck
from skillflow.experiment.t19.metric_adapter import (
    MetricContext,
    adapt_core,
    adapt_replay,
    bind_skill,
)
from skillflow.experiment.t19.replay import ReplaySetup, run_pair
from skillflow.experiment.t19.strict_metrics import alr_metrics, rir_metrics
from skillflow.experiment.t19.tasks import task_variant

ROOT = Path(__file__).resolve().parents[3]


def test_actual_claim_requests_need_same_source_replay(tmp_path: Path) -> None:
    trial = next(t for t in precheck() if t.mechanism == "A1" and t.group == "Monitor")
    skill = task_variant(ROOT, "A1", "attack", "development")
    client = V2FakeClient()
    record, factory = execute(
        ExecutionSetup(ROOT, tmp_path / "core", trial.trial_id, "fake_reference", trial.group),
        skill,
        client,
    )
    core = adapt_core(
        MetricContext(canonical_digest("test-phase"), canonical_digest(trial)),
        trial,
        record,
        bind_skill(skill),
    )
    missing = alr_metrics((core,), (), complete=True)
    assert missing["alr"].value is None
    assert missing["alr"].denominator == 1
    replay = run_pair(
        ReplaySetup(ROOT, tmp_path / "replay", client, lambda _a, _b: None, UnitUsage),
        record,
        skill,
        factory,
        "authorization-claim",
    )
    measured = alr_metrics((core,), (adapt_replay(core, replay),), complete=True)
    assert measured["alr"].denominator == 1
    assert measured["alr"].value == 1


def test_revoked_origin_and_uea_alone_do_not_prove_rir(tmp_path: Path) -> None:
    trial = next(t for t in precheck() if t.mechanism == "M2" and t.group == "Monitor")
    skill = task_variant(ROOT, "M2", "attack", "development")
    client = V2FakeClient()
    record, factory = execute(
        ExecutionSetup(ROOT, tmp_path / "core", trial.trial_id, "fake_reference", trial.group),
        skill,
        client,
    )
    core = adapt_core(
        MetricContext(canonical_digest("test-phase"), canonical_digest(trial)),
        trial,
        record,
        bind_skill(skill),
    )
    pairs = tuple(
        adapt_replay(
            core,
            run_pair(
                ReplaySetup(ROOT, tmp_path / "replay", client, lambda _a, _b: None, UnitUsage),
                record,
                skill,
                factory,
                alias,
            ),
        )
        for alias in ("m2-memory-1", "m2-memory-3")
    )
    assert any(not e.authorized for e in record.data.proof.report.effects)
    assert all(p.proof is not None and p.proof.ci == 0 for p in pairs)
    measured = rir_metrics((core,), pairs, complete=True)
    assert measured["rir_1"].denominator == 1
    assert measured["rir_1"].value == measured["rir_3"].value == 0
