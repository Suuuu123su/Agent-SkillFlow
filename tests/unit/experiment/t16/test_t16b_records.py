import pytest
from pydantic import JsonValue, ValidationError

from skillflow.experiment.t16.dry_run_records import (
    A1_PRESERVED_FIELDS,
    DryRunInterventionAudit,
    T16BDryRunConfig,
)
from skillflow.experiment.t16.preregistration_models import T16Intervention
from skillflow.experiment.t16.provider import PricingStatus, ProviderKind


def provider_payload(kind: ProviderKind = ProviderKind.FAKE) -> dict[str, JsonValue]:
    status = PricingStatus.FAKE_ZERO if kind is ProviderKind.FAKE else PricingStatus.LIVE_PENDING
    return {
        "kind": kind.value,
        "model_id": f"{kind.value}-slot",
        "model_revision": "logic-v1",
        "temperature": 0,
        "reasoning_effort": "none",
        "pricing": {
            "status": status.value,
            "input_per_million_usd": "0",
            "cached_input_per_million_usd": "0",
            "output_per_million_usd": "0",
            "reasoning_per_million_usd": "0",
        },
    }


def config_payload() -> dict[str, JsonValue]:
    return {
        "id": "t16b-test",
        "slots": [
            {"slot_id": "fake-slot-1", "provider": provider_payload()},
            {"slot_id": "fake-slot-2", "provider": provider_payload()},
        ],
        "budget": {
            "allow_live": False,
            "max_total_usd": "1.00",
            "max_cost_per_run_usd": "0.10",
            "max_agent_turns": 3,
            "max_output_tokens_per_turn": 256,
            "max_retries": 1,
        },
        "hypothetical_pricing": {
            "status": "live_pinned",
            "input_per_million_usd": "2.00",
            "cached_input_per_million_usd": "0.20",
            "output_per_million_usd": "8.00",
            "reasoning_per_million_usd": "4.00",
        },
        "cost_profiles": [
            {
                "profile": "short",
                "normal_usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 2,
                    "output_tokens": 3,
                    "reasoning_tokens": 1,
                },
                "worst_case_usage": {
                    "input_tokens": 20,
                    "cached_input_tokens": 0,
                    "output_tokens": 6,
                    "reasoning_tokens": 2,
                },
                "normal_api_calls": 1,
                "worst_case_api_calls": 2,
            },
            {
                "profile": "normal",
                "normal_usage": {
                    "input_tokens": 20,
                    "cached_input_tokens": 4,
                    "output_tokens": 6,
                    "reasoning_tokens": 2,
                },
                "worst_case_usage": {
                    "input_tokens": 40,
                    "cached_input_tokens": 0,
                    "output_tokens": 12,
                    "reasoning_tokens": 4,
                },
                "normal_api_calls": 2,
                "worst_case_api_calls": 4,
            },
            {
                "profile": "m2_multi_session",
                "normal_usage": {
                    "input_tokens": 30,
                    "cached_input_tokens": 6,
                    "output_tokens": 9,
                    "reasoning_tokens": 3,
                },
                "worst_case_usage": {
                    "input_tokens": 60,
                    "cached_input_tokens": 0,
                    "output_tokens": 18,
                    "reasoning_tokens": 6,
                },
                "normal_api_calls": 3,
                "worst_case_api_calls": 6,
            },
        ],
    }


def test_t16b_config_requires_two_distinct_fake_slots_and_closed_live() -> None:
    # Given: 两个纯本地逻辑 Fake Model Slot。
    config = T16BDryRunConfig.model_validate(config_payload())

    # When / Then: 双槽位与零网络预算边界被冻结。
    assert tuple(item.slot_id for item in config.slots) == ("fake-slot-1", "fake-slot-2")
    assert config.budget.allow_live is False
    assert config.budget.max_retries == 1

    duplicate = config_payload()
    duplicate["slots"] = [
        {"slot_id": "same", "provider": provider_payload()},
        {"slot_id": "same", "provider": provider_payload()},
    ]
    with pytest.raises(ValidationError, match="槽位"):
        T16BDryRunConfig.model_validate(duplicate)

    live = config_payload()
    live["slots"] = [
        {"slot_id": "fake-slot-1", "provider": provider_payload(ProviderKind.LIVE)},
        {"slot_id": "fake-slot-2", "provider": provider_payload()},
    ]
    with pytest.raises(ValidationError, match="Fake"):
        T16BDryRunConfig.model_validate(live)


def test_a1_neutralization_audit_allows_only_authorization_claim_removal() -> None:
    # Given: A1 neutralized 的预注册干预审计。
    audit = DryRunInterventionAudit(
        intervention=T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM,
        removed_fields=("authorization_claim",),
        preserved_fields=A1_PRESERVED_FIELDS,
    )

    # When / Then: 仅声明被删除，其余能力控制量全部保留。
    assert audit.removed_fields == ("authorization_claim",)
    with pytest.raises(ValidationError, match="只允许删除"):
        DryRunInterventionAudit(
            intervention=T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM,
            removed_fields=("authorization_claim", "tool_actions"),
            preserved_fields=A1_PRESERVED_FIELDS,
        )
