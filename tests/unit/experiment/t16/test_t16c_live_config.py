from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.provider import (
    PricingRates,
    PricingStatus,
    ProviderConfig,
    ProviderKind,
    ReasoningEffort,
)
from skillflow.validation import validate_yaml_document

ROOT = Path(__file__).parents[4]


def _provider(**changes: object) -> ProviderConfig:
    payload: dict[str, object] = {
        "kind": ProviderKind.LIVE,
        "model_id": "gpt-5.6-luna",
        "model_revision": "gpt-5.6-luna",
        "temperature": None,
        "reasoning_effort": ReasoningEffort.MEDIUM,
        "pricing": PricingRates(
            status=PricingStatus.LIVE_PINNED,
            input_per_million_usd=Decimal("0.20"),
            cached_input_per_million_usd=Decimal("0.02"),
            cache_write_per_million_usd=Decimal("0.25"),
            output_per_million_usd=Decimal("1.20"),
            reasoning_per_million_usd=Decimal("1.20"),
        ),
    }
    payload.update(changes)
    return ProviderConfig.model_validate(payload)


def _budget(**changes: object) -> BudgetConfig:
    payload: dict[str, object] = {
        "allow_live": True,
        "max_total_usd": Decimal("20.00"),
        "max_cost_per_run_usd": Decimal("0.05"),
        "max_agent_turns": 12,
        "max_output_tokens_per_turn": 512,
        "max_retries": 1,
    }
    payload.update(changes)
    return BudgetConfig.model_validate(payload)


def test_t16c_config_freezes_luna_price_and_twenty_dollar_ceiling() -> None:
    config = T16CLiveConfig(provider=_provider(), budget=_budget())

    assert config.provider.model_id == "gpt-5.6-luna"
    assert config.provider.temperature is None
    assert config.budget.max_total_usd == Decimal("20.00")
    assert config.smoke_max_total_usd == Decimal("0.50")
    assert config.max_smoke_attempts == 3
    assert config.store_responses is False
    assert config.transport_retries == 0


@pytest.mark.parametrize(
    ("provider", "budget"),
    [
        (_provider(model_id="gpt-5.6-sol"), _budget()),
        (_provider(temperature=0.2), _budget()),
        (
            _provider(
                pricing=PricingRates(
                    status=PricingStatus.LIVE_PENDING,
                    input_per_million_usd=Decimal(0),
                    cached_input_per_million_usd=Decimal(0),
                    output_per_million_usd=Decimal(0),
                    reasoning_per_million_usd=Decimal(0),
                )
            ),
            _budget(),
        ),
        (_provider(), _budget(allow_live=False)),
        (_provider(), _budget(max_total_usd=Decimal("20.01"))),
        (_provider(), _budget(max_retries=2)),
    ],
)
def test_t16c_config_rejects_unfrozen_or_overbroad_live_execution(
    provider: ProviderConfig,
    budget: BudgetConfig,
) -> None:
    with pytest.raises(ValidationError):
        T16CLiveConfig(provider=provider, budget=budget)


def test_t16c_config_has_no_credential_field() -> None:
    payload = {
        "provider": _provider().model_dump(mode="python"),
        "budget": _budget().model_dump(mode="python"),
        "api_key": "must-not-be-stored",
    }

    with pytest.raises(ValidationError, match="extra_forbidden"):
        T16CLiveConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("budget", "smoke_max_total_usd"),
    [
        (_budget(max_cost_per_run_usd=Decimal("0.051")), Decimal("0.50")),
        (_budget(max_agent_turns=17), Decimal("0.50")),
        (_budget(max_output_tokens_per_turn=513), Decimal("0.50")),
        (_budget(), Decimal("0.51")),
    ],
)
def test_t16c_config_rejects_execution_limits_above_frozen_ceilings(
    budget: BudgetConfig,
    smoke_max_total_usd: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        T16CLiveConfig(
            provider=_provider(),
            budget=budget,
            smoke_max_total_usd=smoke_max_total_usd,
        )


def test_t16c_config_rejects_more_than_three_smoke_attempts() -> None:
    with pytest.raises(ValidationError):
        T16CLiveConfig(
            provider=_provider(),
            budget=_budget(),
            max_smoke_attempts=4,
        )


def test_static_t16c_config_freezes_user_budget_without_credentials() -> None:
    path = ROOT / "experiments" / "t16" / "t16c_live.yaml"

    config = validate_yaml_document(path, T16CLiveConfig)

    assert config.budget.max_total_usd == Decimal("20.00")
    assert config.smoke_max_total_usd == Decimal("0.50")
    assert config.budget.max_cost_per_run_usd == Decimal("0.05")
    assert config.budget.max_output_tokens_per_turn == 512
    assert "api_key" not in path.read_text(encoding="utf-8").lower()
