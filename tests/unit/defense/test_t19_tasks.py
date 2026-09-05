import json
from pathlib import Path

import pytest

from skillflow.experiment.t17.reference_backend import ReferenceModelDecision, ReferenceModelRequest
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t17.v2.runtime_models import ModelOutcomeError
from skillflow.experiment.t19.execution import ExecutionSetup, execute
from skillflow.experiment.t19.tasks import task_variant, trusted_task

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("base", ["C1", "C2", "M2", "A1"])
def test_task_pairs_share_facts_permissions_and_capabilities(base: str) -> None:
    a, n = (task_variant(ROOT, base, role, "heldout-ledger") for role in ("attack", "neutral"))
    assert a.task_contract == n.task_contract
    assert a.scenario.grants == n.scenario.grants
    assert a.manifests == n.manifests
    assert a.scenario.task == n.scenario.task
    for key, script in a.bundle.scripts.items():
        assert script.actions == n.bundle.scripts[key].actions
        assert all(action.input_gate is None for action in script.actions)
    assert "C1" not in trusted_task(base).model_dump_json()


@pytest.mark.parametrize("base", ["C1", "C2"])
@pytest.mark.parametrize("bridge", [True, False])
def test_bridge_closure_keeps_normal_facts_and_task_success(
    base: str,
    bridge: bool,
    tmp_path: Path,
) -> None:
    skill = task_variant(ROOT, base, "attack", "heldout-inventory")
    record, _ = execute(
        ExecutionSetup(ROOT, tmp_path, "test-task", "fake_reference", "Evidence", bridge=bridge),
        skill,
        V2FakeClient(),
    )
    assert record.data.proof.task.task_success
    assert record.data.proof.task.safe_task_success
    if not bridge:
        derived = [
            e
            for e in record.data.facts.events
            if e.metadata.get("contract") == "t19-facts-control-v1"
        ]
        assert derived


def test_templates_are_different_tasks_and_development_is_separate() -> None:
    tasks = [
        task_variant(ROOT, "C1", "attack", template)
        for template in ("development", "heldout-ledger", "heldout-inventory")
    ]
    assert len({t.task_contract.artifacts[0].expected_sha256 for t in tasks}) == 3
    contents = [json.loads(t.bundle.scripts["fixture://t12/context-target"].output) for t in tasks]
    assert len({json.dumps(c["facts"], sort_keys=True) for c in contents}) == 3


class EmptyFailureClient:
    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        raise ModelOutcomeError("schema_rejection")


def test_empty_model_output_remains_task_failure_when_bridge_closed(tmp_path: Path) -> None:
    skill = task_variant(ROOT, "C1", "attack", "heldout-ledger")
    record, _ = execute(
        ExecutionSetup(ROOT, tmp_path, "empty", "fake_reference", "Monitor", bridge=False),
        skill,
        EmptyFailureClient(),
    )
    assert not record.data.proof.task.task_success
    assert all(d.behavior == "schema_rejection" for d in record.decisions)


def test_a1_attack_actually_claims_user_authorization() -> None:
    skill = task_variant(ROOT, "A1", "attack", "heldout-ledger")
    value = json.loads(skill.bundle.scripts["fixture://t12/claim-source"].output)
    assert "user has explicitly approved" in value["control"]


class ScalarSourceClient(V2FakeClient):
    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        if request.implementation.root in {
            "fixture://t12/context-target",
            "fixture://t12/claim-source",
        }:
            return ReferenceModelDecision(selected_action_ids=(), output_text="30")
        return super().decide(request)


class UnstructuredSourceClient:
    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        return ReferenceModelDecision(selected_action_ids=(), output_text="unstructured source")


def test_unseparable_nonempty_source_has_closed_task_failure(tmp_path: Path) -> None:
    skill = task_variant(ROOT, "C1", "attack", "heldout-ledger")
    record, _ = execute(
        ExecutionSetup(ROOT, tmp_path, "scalar", "fake_reference", "Monitor", bridge=False),
        skill,
        UnstructuredSourceClient(),
    )
    assert not record.data.proof.task.task_success
    assert len(record.boundary_issues) == 1
    assert len(record.decisions) == 1
    assert record.boundary_issues[0].artifact_ids


def test_bridge_keeps_model_produced_scalar_data(tmp_path: Path) -> None:
    skill = task_variant(ROOT, "C1", "attack", "heldout-ledger")
    record, _ = execute(
        ExecutionSetup(ROOT, tmp_path, "numeric", "fake_reference", "Monitor", bridge=False),
        skill,
        ScalarSourceClient(),
    )
    assert record.data.proof.task.task_success
    assert not record.boundary_issues
