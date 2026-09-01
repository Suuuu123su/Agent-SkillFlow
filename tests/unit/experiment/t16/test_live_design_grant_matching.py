"""T16-C 预注册静态 Grant 结构匹配的专门回归测试。"""

from datetime import timedelta
from pathlib import Path

import pytest

from skillflow.experiment.t16.live_design_context import (
    LiveTargetGrantMatchIndeterminateError,
    has_matching_target_grant,
)
from skillflow.models.enums import Lifetime, Scope
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document

ROOT = Path(__file__).parents[4]


def _scenario(relative_path: str) -> Scenario:
    return validate_yaml_document(ROOT / relative_path, Scenario)


def _replace_grant(scenario: Scenario, grant_id: str, **changes: object) -> Scenario:
    initial = tuple(
        grant.model_copy(update=changes) if grant.grant_id == grant_id else grant
        for grant in scenario.grants
    )
    sessions = tuple(
        session.model_copy(
            update={
                "steps": tuple(
                    step.model_copy(update={"grant": step.grant.model_copy(update=changes)})
                    if step.grant is not None and step.grant.grant_id == grant_id
                    else step
                    for step in session.steps
                )
            }
        )
        for session in scenario.sessions
    )
    return scenario.model_copy(update={"grants": initial, "sessions": sessions})


def test_static_match_uses_terminal_invoker_and_canonical_grant_semantics() -> None:
    a1 = _scenario("scenarios/attacks/a1_implicit_text_authorization.yaml")
    a2 = _scenario("scenarios/benign/a2_structured_confirmation.yaml")

    assert has_matching_target_grant(a1, ("authorization-send",)) is False
    assert has_matching_target_grant(a2, ("authorization-send",)) is True


def test_static_match_rejects_wrong_grantee_even_when_resources_match() -> None:
    scenario = _replace_grant(
        _scenario("scenarios/benign/a2_structured_confirmation.yaml"),
        "grant-confirmed-send",
        grantee_id="claim-source",
    )

    assert has_matching_target_grant(scenario, ("authorization-send",)) is False


@pytest.mark.parametrize(
    "changes",
    [
        {"valid_from_offset": timedelta(seconds=1), "expires_offset": None},
        {"valid_from_offset": timedelta(hours=-2), "expires_offset": timedelta(hours=-1)},
    ],
)
def test_static_match_rejects_not_yet_valid_or_expired_grant(
    changes: dict[str, timedelta | None],
) -> None:
    scenario = _scenario("scenarios/benign/a2_structured_confirmation.yaml")
    valid_from_offset = changes["valid_from_offset"]
    assert valid_from_offset is not None
    expires_offset = changes["expires_offset"]
    scenario = _replace_grant(
        scenario,
        "grant-confirmed-send",
        valid_from=scenario.clock.start + valid_from_offset,
        expires_at=(None if expires_offset is None else scenario.clock.start + expires_offset),
    )

    assert has_matching_target_grant(scenario, ("authorization-send",)) is False


@pytest.mark.parametrize(
    "changes",
    [
        {"task_id": "different-task"},
        {"lifetime": Lifetime.SESSION, "session_id": "different-session"},
        {"scope": Scope.EXACT_FILE},
    ],
)
def test_static_match_rejects_cross_boundary_or_uncovered_scope(
    changes: dict[str, object],
) -> None:
    scenario = _replace_grant(
        _scenario("scenarios/benign/a2_structured_confirmation.yaml"),
        "grant-confirmed-send",
        **changes,
    )

    assert has_matching_target_grant(scenario, ("authorization-send",)) is False


def test_static_match_respects_explicit_auth_revoke_fact() -> None:
    scenario = _scenario("scenarios/benign/a2_structured_confirmation.yaml")

    assert (
        has_matching_target_grant(
            scenario,
            ("authorization-send",),
            revoked_grant_ids=frozenset({"grant-confirmed-send"}),
        )
        is False
    )


def test_static_match_rejects_call_lifetime_without_observed_call_id() -> None:
    scenario = _replace_grant(
        _scenario("scenarios/benign/a2_structured_confirmation.yaml"),
        "grant-confirmed-send",
        lifetime=Lifetime.CALL,
        call_id="call-not-observed-by-static-design",
    )

    with pytest.raises(LiveTargetGrantMatchIndeterminateError, match="不是运行期 Hook"):
        has_matching_target_grant(scenario, ("authorization-send",))


def test_static_match_does_not_preload_confirmation_after_target_invocation() -> None:
    scenario = _scenario("scenarios/benign/a2_structured_confirmation.yaml")
    session = scenario.sessions[0]
    reordered = session.model_copy(
        update={"steps": (session.steps[0], session.steps[2], session.steps[1])}
    )
    scenario = scenario.model_copy(update={"sessions": (reordered,)})

    assert has_matching_target_grant(scenario, ("authorization-send",)) is False
