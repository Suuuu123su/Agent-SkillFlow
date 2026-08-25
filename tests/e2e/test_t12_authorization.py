from pathlib import Path

from skillflow.analysis.authorization_laundering import (
    AuthorizationAttemptFact,
    AuthorizationClaimNeutralization,
    BaselineReason,
    calculate_alr,
)
from skillflow.benchmark.replay import ReplayRunner
from skillflow.benchmark.replay_models import ReplayPairResult
from skillflow.benchmark.runner import ScenarioRunner, ScenarioRunResult
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.models.advanced_metrics import AuthorizationAttemptClass
from skillflow.models.enums import Decision
from skillflow.store.sqlite_store import SqliteEventStore

ROOT = Path("scenarios")


def _run(path: Path, root: Path, seed: str) -> tuple[ScenarioRunResult, ReplayPairResult]:
    scripts, decisions = t12_fixture_registry()
    result = ScenarioRunner(scripts, decisions).run(path, root / "run", seed)
    replay = ReplayRunner(scripts, decisions).run(path, root / "replay", seed)
    return result, replay.pairs[0]


def _attempt(
    result: ScenarioRunResult,
    replay: ReplayPairResult,
    reason: BaselineReason,
) -> AuthorizationAttemptFact:
    claim_id = result.artifact_ids_by_alias["authorization-claim"]
    with SqliteEventStore(result.database_path) as store:
        effects = store.iter_run_effects(result.run_id)
        assert len(effects) == 1
        effect = effects[0]
        decision = store.get_decision(effect.decision_id)
        claim = store.get_artifact(claim_id)
    assert decision is not None
    assert claim is not None
    neutral_database = replay.report_path.parent / "neutral" / "state.sqlite"
    with SqliteEventStore(neutral_database) as store:
        neutral_effects = store.iter_run_effects(replay.report.neutral_run_id)
        decisions = tuple(
            decision
            for event in store.iter_run_events(replay.report.neutral_run_id)
            if event.decision_id is not None
            for decision in (store.get_decision(event.decision_id),)
            if decision is not None
        )
    assert decisions
    return AuthorizationAttemptFact(
        authorization_request_id=effect.request_event_id,
        has_matching_grant=bool(decision.matched_grant_ids),
        authorization_claim_artifact_id=claim_id,
        authorization_claim_trust=claim.observed_label.trust,
        decision_basis_artifact_ids=decision.decision_basis_artifact_ids,
        baseline_reason=reason,
        original_receipt_ids=tuple(receipt.receipt_id for receipt in result.receipts),
        neutralization=AuthorizationClaimNeutralization(
            replay_id=replay.report.replay_id,
            neutralized_claim_artifact_id=claim_id,
            original_non_claim_inputs_hash=replay.report_path.name,
            neutral_non_claim_inputs_hash=replay.report_path.name,
        ),
        neutral_baseline_result=decisions[-1].baseline_result,
        neutral_receipt_ids=tuple(
            effect.tool_receipt_id
            for effect in neutral_effects
            if effect.tool_receipt_id is not None
        ),
        evidence_ids=(decision.decision_id, replay.report.replay_id),
    )


def test_a1_and_a2_separate_text_claim_from_real_grant(tmp_path: Path) -> None:
    a1_run, a1_replay = _run(
        ROOT / "attacks" / "a1_implicit_text_authorization.yaml",
        tmp_path / "a1",
        "t12-a1",
    )
    a2_run, a2_replay = _run(
        ROOT / "benign" / "a2_structured_confirmation.yaml",
        tmp_path / "a2",
        "t12-a2",
    )
    a1 = _attempt(a1_run, a1_replay, BaselineReason.IMPLICIT_TEXT_AUTHORIZATION)
    a2 = _attempt(a2_run, a2_replay, BaselineReason.STRUCTURED_CONFIRMATION)

    a1_metrics = calculate_alr((a1,))
    a2_metrics = calculate_alr((a2,))

    assert a1.has_matching_grant is False
    assert a1.authorization_claim_artifact_id in a1.decision_basis_artifact_ids
    assert a1.neutral_baseline_result in {Decision.CONFIRM, Decision.DENY}
    assert a1_replay.report.ci == 1
    assert a1_metrics.alr.value == 1.0
    assert (
        a1_metrics.attempts[0].classification is AuthorizationAttemptClass.AUTHORIZATION_LAUNDERING
    )
    assert a2.has_matching_grant is True
    assert a2_replay.report.ci == 0
    assert a2_metrics.alr.value == 0.0
