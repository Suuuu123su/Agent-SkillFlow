import pytest
from pydantic import JsonValue, ValidationError

from skillflow.analysis.counterfactual import compute_scripted_ci
from skillflow.models.reports import ConfirmedInfluenceEdge, ReplayRiskReport


def _report_payload() -> dict[str, JsonValue]:
    return {
        "schema_version": "0.1",
        "report_scope": "replay",
        "replay_id": "replay-1",
        "original_run_id": "run-original",
        "neutral_run_id": "run-neutral",
        "intervention_artifact_id": "artifact-source",
        "original_intervention_artifact_id": "artifact-original-copy",
        "neutral_intervention_artifact_id": "artifact-neutral-copy",
        "observed_effect_ids": ["effect-1"],
        "original_effect_ids": ["effect-1"],
        "neutral_effect_ids": [],
        "removed_effect_ids": ["effect-1"],
        "added_effect_ids": [],
        "y_original": True,
        "y_neutral": False,
        "ci": 1,
        "confirmed_influence_edges": [
            {
                "source_artifact_id": "artifact-source",
                "target_effect_id": "effect-1",
                "relation": "INFLUENCE_CONFIRMED",
            }
        ],
    }


@pytest.mark.parametrize(
    ("original", "neutral", "expected"),
    [(True, False, 1), (True, True, 0), (False, False, 0), (False, True, -1)],
)
def test_scripted_ci_is_signed_difference(
    original: bool,
    neutral: bool,
    expected: int,
) -> None:
    assert compute_scripted_ci(original, neutral) == expected


def test_replay_report_requires_a_typed_confirmed_edge_for_nonzero_ci() -> None:
    report = ReplayRiskReport.model_validate(_report_payload())

    assert report.ci == 1
    assert report.confirmed_influence_edges == (
        ConfirmedInfluenceEdge(
            source_artifact_id="artifact-source",
            target_effect_id="effect-1",
        ),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("neutral_run_id", "run-original"),
        ("ci", 0),
        ("observed_effect_ids", []),
        ("removed_effect_ids", []),
    ],
)
def test_replay_report_rejects_inconsistent_pair_facts(field: str, value: JsonValue) -> None:
    payload = _report_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        ReplayRiskReport.model_validate(payload)


def test_zero_ci_forbids_confirmed_influence_edges() -> None:
    payload = _report_payload()
    payload.update(
        {
            "observed_effect_ids": ["effect-1"],
            "neutral_effect_ids": ["effect-1"],
            "removed_effect_ids": [],
            "y_neutral": True,
            "ci": 0,
            "confirmed_influence_edges": [],
        }
    )

    report = ReplayRiskReport.model_validate(payload)

    assert report.confirmed_influence_edges == ()


def test_negative_ci_targets_an_effect_added_by_the_neutral_branch() -> None:
    payload = _report_payload()
    payload.update(
        {
            "observed_effect_ids": ["effect-neutral"],
            "original_effect_ids": [],
            "neutral_effect_ids": ["effect-neutral"],
            "removed_effect_ids": [],
            "added_effect_ids": ["effect-neutral"],
            "y_original": False,
            "y_neutral": True,
            "ci": -1,
            "confirmed_influence_edges": [
                {
                    "source_artifact_id": "artifact-source",
                    "target_effect_id": "effect-neutral",
                    "relation": "INFLUENCE_CONFIRMED",
                }
            ],
        }
    )

    report = ReplayRiskReport.model_validate(payload)

    assert report.ci == -1
