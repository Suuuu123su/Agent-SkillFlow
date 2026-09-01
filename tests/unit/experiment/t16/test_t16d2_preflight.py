from decimal import Decimal
from pathlib import Path

import pytest

from skillflow.experiment.t16.task_success_live_config import build_t16d2_live_config
from skillflow.experiment.t16.task_success_live_preflight import (
    T16D2EnvironmentError,
    load_t16d2_environment,
    load_t16d2_inputs,
    select_canary_trials,
)

ROOT = Path(__file__).parents[4]


def _environment() -> dict[str, str]:
    return {
        "SKILLFLOW_PROVIDER": "openai",
        "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
        "SKILLFLOW_MAX_USD": "3",
        "SKILLFLOW_LIVE_APPROVED": "1",
    }


def test_t16d2_environment_is_exact_and_has_no_credential_field() -> None:
    environment = load_t16d2_environment(_environment())

    assert environment.provider == "openai"
    assert environment.model_id == "gpt-5.6-luna"
    assert environment.max_total_usd == Decimal(3)
    assert "key" not in environment.model_dump_json().lower()


def test_t16d2_live_config_applies_frozen_multi_session_budget_intersection() -> None:
    config = build_t16d2_live_config(ROOT)

    assert config.budget.allow_live is True
    assert config.budget.max_total_usd == Decimal(3)
    assert config.budget.max_cost_per_run_usd == Decimal("0.05")
    assert config.budget.max_agent_turns == 8
    assert config.budget.max_output_tokens_per_turn == 512
    assert config.budget.max_retries == 1


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SKILLFLOW_PROVIDER", "other"),
        ("SKILLFLOW_MODEL_ID", "latest"),
        ("SKILLFLOW_MAX_USD", "3.01"),
        ("SKILLFLOW_LIVE_APPROVED", "0"),
    ],
)
def test_t16d2_environment_rejects_any_live_authorization_drift(
    name: str,
    value: str,
) -> None:
    environment = _environment()
    environment[name] = value

    with pytest.raises(T16D2EnvironmentError):
        load_t16d2_environment(environment)


def test_canary_selection_is_deterministic_and_preserves_complete_groups() -> None:
    inputs = load_t16d2_inputs(ROOT)

    canary = select_canary_trials(inputs.matrix)

    assert len(canary) == 11
    assert tuple(item.condition_id for item in canary) == (
        "b0",
        "g0",
        "c1-p00",
        "c1-p01",
        "c1-p10",
        "c1-p11",
        "m2-control",
        "m2-target",
        "a1-claim",
        "a1-neutralized",
        "a2-structured-confirmation",
    )
    paired = tuple(item for item in canary if item.condition_id.startswith("c1-"))
    assert len({item.semantic_instance_id for item in paired}) == 1
    assert len({item.repeat_index for item in paired}) == 1
