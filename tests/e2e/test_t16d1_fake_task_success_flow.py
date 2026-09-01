import socket
from pathlib import Path

import pytest

from skillflow.experiment.t16.provider import (
    ProviderKind,
)
from skillflow.experiment.t16.task_success_fake_flow import FakeReceiptInput
from skillflow.experiment.t16.task_success_output import StructuredTaskResultV3
from skillflow.experiment.t16.task_success_registration import load_task_success_registry
from tests.e2e.t16d1_fake_support import (
    RunOptions,
    run_fixture,
    structured_output,
)

ROOT = Path(__file__).parents[2]
REGISTRY_PATH = ROOT / "experiments" / "t16" / "task_success_assertions_v3.yaml"


def test_all_12_conditions_complete_through_fake_provider_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked_network(
        _address: tuple[str, int],
        _timeout: float | None = None,
        _source_address: tuple[str, int] | None = None,
    ) -> None:
        detail = "unexpected network"
        raise AssertionError(detail)

    monkeypatch.setattr(socket, "create_connection", blocked_network)
    registry = load_task_success_registry(REGISTRY_PATH)

    records = tuple(
        run_fixture(
            specification,
            structured_output(specification.task_output_contract_id).model_dump_json(),
        )
        for specification in registry.conditions
    )

    assert len(records) == 12
    assert all(item.task_success_result.task_success is True for item in records)
    assert all(item.provider_kind is ProviderKind.FAKE for item in records)
    assert all(item.estimated_cost_usd == 0 for item in records)


def test_task_success_and_target_effect_remain_two_dimensions() -> None:
    specification = load_task_success_registry(REGISTRY_PATH).conditions[2]
    correct = structured_output(specification.task_output_contract_id).model_dump_json()
    target_receipt = FakeReceiptInput(
        effect_alias="context-harm",
        session_id="session-0",
        payload=b"secret-canary-never-persist",
    )

    both_true = run_fixture(
        specification,
        correct,
        RunOptions(
            receipt_inputs=(target_receipt,),
            target_effect_aliases=("context-harm",),
        ),
    )
    both_false = run_fixture(
        specification,
        StructuredTaskResultV3(
            task_status="completed",
            result_kind="normal_processing",
            fact_ids=("wrong.fact",),
            value_id="wrong.value",
        ).model_dump_json(),
    )

    assert (both_true.task_success_result.task_success, both_true.target_effect_executed) == (
        True,
        True,
    )
    assert (both_false.task_success_result.task_success, both_false.target_effect_executed) == (
        False,
        False,
    )
    assert "secret-canary-never-persist" not in both_true.model_dump_json()


def test_refusal_schema_rejection_and_missing_hook_are_separate() -> None:
    specification = load_task_success_registry(REGISTRY_PATH).conditions[2]
    correct = structured_output(specification.task_output_contract_id).model_dump_json()

    refusal = run_fixture(specification, correct, RunOptions(refusal=True))
    schema_rejection = run_fixture(
        specification,
        '{"schema_version":"3.0","artifact_alias":"model-forged"}',
    )
    unavailable = run_fixture(
        specification,
        correct,
        RunOptions(artifact_registry_available=False, produce_artifact=False),
    )

    assert refusal.task_success_result.task_success is False
    assert refusal.refusal is True
    assert refusal.infrastructure_invalid is False
    assert refusal.schema_rejection is False
    assert schema_rejection.task_success_result.task_success is False
    assert schema_rejection.schema_rejection is True
    assert schema_rejection.observation_valid is True
    assert unavailable.task_success_result.task_success is None
