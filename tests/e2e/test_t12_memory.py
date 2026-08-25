from datetime import UTC, datetime, timedelta
from pathlib import Path

from skillflow.analysis.residual_influence import calculate_rir
from skillflow.benchmark.replay import ReplayRunner
from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.graph.security import SecurityGraph
from skillflow.models.reports import ReplayRiskReport
from skillflow.models.residual_metrics import (
    AttributionKind,
    ResidualActionEvidence,
    ResidualRunObservation,
    SkillRevocationRecord,
)
from skillflow.store.sqlite_store import SqliteEventStore

ROOT = Path("scenarios")
REVOKED_AT = datetime(2026, 8, 25, tzinfo=UTC)


def _replay_runner() -> ReplayRunner:
    scripts, decisions = t12_fixture_registry()
    return ReplayRunner(scripts, decisions)


def test_m1_restores_cross_session_path_and_confirms_memory_influence(
    tmp_path: Path,
) -> None:
    scripts, decisions = t12_fixture_registry()
    run = ScenarioRunner(scripts, decisions).run(
        ROOT / "attacks" / "m1_cross_session_memory.yaml",
        tmp_path / "m1-run",
        seed="t12-m1",
    )
    with SqliteEventStore(run.database_path) as store:
        graph = SecurityGraph.from_store(store, run.run_id)
    replay = _replay_runner().run(
        ROOT / "attacks" / "m1_cross_session_memory.yaml",
        tmp_path / "m1-replay",
        seed="t12-m1-replay",
    )

    assert graph.find_cross_session_paths(run.run_id)
    assert graph.find_skill_to_effect_paths("memory-skill-a")
    assert replay.pairs[0].report.ci == 1
    assert len(replay.pairs[0].report.confirmed_influence_edges) == 1


def test_m2_replay_supports_strict_rir_one_and_three(tmp_path: Path) -> None:
    attack = _replay_runner().run(
        ROOT / "attacks" / "m2_revoked_memory_residual.yaml",
        tmp_path / "m2-attack",
        seed="t12-m2",
    )
    control = _replay_runner().run(
        ROOT / "benign" / "m2_revoked_memory_control.yaml",
        tmp_path / "m2-control",
        seed="t12-m2-control",
    )
    attack_pairs = {pair.target_alias: pair.report for pair in attack.pairs}
    control_pairs = {pair.target_alias: pair.report for pair in control.pairs}

    assert tuple(report.ci for report in attack_pairs.values()) == (1, 1)
    assert tuple(report.ci for report in control_pairs.values()) == (0, 0)
    revocation = SkillRevocationRecord(
        skill_id="memory-skill-a",
        revoke_event_id="m2-revoke-event",
        session_index=0,
        revoked_at=REVOKED_AT,
    )
    runs = tuple(_residual_run(offset, attack_pairs[f"m2-memory-{offset}"]) for offset in (1, 3))

    rir_1 = calculate_rir(revocation, runs, 1)
    rir_3 = calculate_rir(revocation, runs, 3)

    assert (rir_1.numerator, rir_1.denominator, rir_1.value) == (1, 1, 1.0)
    assert (rir_3.numerator, rir_3.denominator, rir_3.value) == (1, 1, 1.0)


def _residual_run(offset: int, report: ReplayRiskReport) -> ResidualRunObservation:
    edges = report.confirmed_influence_edges
    actions = tuple(
        ResidualActionEvidence(
            effect_id=edge.target_effect_id,
            receipt_id=f"receipt-for-{edge.target_effect_id}",
            unauthorized=True,
            attribution=AttributionKind.INFLUENCE_CONFIRMED,
            attributed_skill_id="memory-skill-a",
            attribution_evidence_ids=(report.replay_id,),
        )
        for edge in edges
    )
    return ResidualRunObservation(
        run_id=f"m2-offset-{offset}",
        session_index=offset,
        started_at=REVOKED_AT + timedelta(hours=offset),
        valid=True,
        actions=actions,
    )
