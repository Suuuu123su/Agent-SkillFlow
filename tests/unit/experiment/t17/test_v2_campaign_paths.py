"""预算、准备和阶段错误的真实控制分支；所有执行与传输均为本地替身。"""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import SecretStr
from tests.unit.experiment.t17.v2_test_campaign_case import (
    control_gate,
    control_outcome,
    prepared_case,
)

from skillflow.experiment.errors import ExperimentCommandError
from skillflow.experiment.t16.openai_responses import ResponsesTransport
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17.v2 import campaign, campaign_setup
from skillflow.experiment.t17.v2.campaign_models import CredentialInputError
from skillflow.experiment.t17.v2.campaign_setup import PreparedCampaign
from skillflow.experiment.t17.v2.run_models import StageResult


@pytest.fixture
def prepared(t17_cli_root: Path, request: pytest.FixtureRequest) -> PreparedCampaign:
    return prepared_case(t17_cli_root / request.node.name)


def runtime(prepared: PreparedCampaign) -> campaign.CampaignRuntime:
    transport = Mock(spec=ResponsesTransport)
    transport.post_json.side_effect = AssertionError("测试禁止网络请求")
    return campaign.CampaignRuntime(prepared, SecretStr("synthetic-secret"), transport)


@pytest.mark.parametrize("blank", ["", "   "])
def test_empty_key_never_creates_runtime(blank: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(campaign.getpass, "getpass", lambda _: blank)
    with pytest.raises(CredentialInputError, match="v2_empty_credential"):
        campaign.read_campaign_key()


@pytest.mark.parametrize("failed_at", [None, 1])
def test_campaign_closes_each_outcome_and_stops_at_first_failure(
    prepared: PreparedCampaign, failed_at: int | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        campaign_setup, "claim_path", lambda _: prepared.setup.output.parent / "claim"
    )
    calls = []

    def stage(current: campaign.CampaignRuntime, index: int, previous: tuple) -> object:
        assert current.secret.get_secret_value() == "synthetic-secret"
        assert len(previous) == index
        calls.append(index)
        return control_outcome(prepared, index, passed=index != failed_at)

    monkeypatch.setattr(campaign, "run_one_stage", stage)
    result = campaign.run_campaign(runtime(prepared))
    assert calls == (list(range(5)) if failed_at is None else [0, 1])
    assert result.all_stages_finished is (failed_at is None)
    assert len(list(prepared.setup.output.glob("campaign-after-*.json"))) == len(calls)
    text = (prepared.setup.output / "campaign-result.json").read_text(encoding="utf-8")
    assert "synthetic-secret" not in text
    assert result.estimated_cost_usd == 0


@pytest.mark.parametrize("failure", ["none", "gate", "run", "export"])
def test_stage_saves_budget_before_execution_and_preserves_safe_failure(
    prepared: PreparedCampaign, failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        campaign, "verify_protocol", lambda *_: (prepared.configuration, prepared.matrices)
    )
    raw = prepared.setup.output / "canary/attempt-01/raw"
    result = StageResult(
        phase=prepared.phases[0],
        cores=(),
        replays=(),
        gate=control_gate(prepared, 0, passed=failure != "gate"),
    )

    def run(setup: object) -> StageResult:
        assert (raw.parent / "budget-proposal.json").is_file()
        assert (raw.parent / "approved-live-config.json").is_file()
        if failure == "run":
            raise RuntimeError("do-not-print-private-message")
        raw.mkdir()
        (raw / "raw-manifest.json").write_text("{}", encoding="utf-8")
        return result

    def export(root: Path, output: Path, loaded: tuple) -> object:
        if failure == "export":
            raise OSError("do-not-print-private-message")
        output.mkdir()
        (output / "dataset-manifest.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(all_provided_stages_passed=failure != "gate")

    monkeypatch.setattr(campaign, "run_stage", run)
    monkeypatch.setattr(campaign, "load_stage", lambda *_: SimpleNamespace(api_usage=()))
    monkeypatch.setattr(campaign, "export_dataset", export)
    result = campaign.run_one_stage(runtime(prepared), 0, ())
    assert (
        result.status
        == {"none": "passed", "gate": "failed", "run": "failed", "export": "postprocessing_failed"}[
            failure
        ]
    )
    assert (raw.parent / "stage-result.json").is_file()
    assert "do-not-print-private-message" not in result.model_dump_json()
    assert "synthetic-secret" not in result.model_dump_json()
    assert (result.raw_manifest is None) is (failure == "run")


@pytest.mark.parametrize("drift", ["configuration", "manifest", "phase"])
def test_request_boundary_rejects_protocol_drift_before_output(
    prepared: PreparedCampaign, drift: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = prepared.configuration
    if drift == "configuration":
        config = config.model_copy(update={"protocol_id": "unexpected-version"})
    monkeypatch.setattr(campaign, "verify_protocol", lambda *_: (config, prepared.matrices))
    if drift == "manifest":
        (prepared.setup.protocol / "protocol-manifest.json").write_text("{}", encoding="utf-8")
    if drift == "phase":
        changed = prepared.phases[0].model_copy(update={"protocol_id": "unexpected-version"})
        (prepared.setup.protocol / "phase-canary.json").write_text(
            changed.model_dump_json(), encoding="utf-8"
        )
    with pytest.raises(ValueError, match=r"v2_(approved_protocol|prepared_phase)_drift"):
        campaign.run_one_stage(runtime(prepared), 0, ())
    assert not prepared.setup.output.exists()


def test_prior_gates_and_same_model_samples_control_next_budget(
    prepared: PreparedCampaign, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="previous_stage_gate"):
        campaign.budget_proposal(prepared, 1, ())
    prior = control_outcome(prepared, 0)
    usage = TokenUsage(input_tokens=10, cached_input_tokens=0, output_tokens=2, reasoning_tokens=1)
    events = (
        SimpleNamespace(event_type="request", usage=None),
        SimpleNamespace(event_type="response", model_revision="other-model", usage=usage),
        SimpleNamespace(
            event_type="response",
            model_revision=prepared.matrices[1].provider.model_revision,
            usage=usage,
        ),
    )
    monkeypatch.setattr(campaign, "read_journal", lambda _: events)
    proposal = campaign.budget_proposal(prepared, 1, (prior,))
    assert proposal.projected_from == "prior_same_model_responses"
    assert proposal.observed_responses == 1
    assert proposal.attempt_budget.max_total_usd == prepared.plan.stages[1].budget.max_total_usd
    assert proposal.remaining_approved_usd == prepared.approval.approved_max_total_usd


def test_unreadable_journal_keeps_full_reservation(t17_cli_root: Path) -> None:
    raw = t17_cli_root / "unreadable-journal"
    raw.mkdir()
    assert campaign.partial_usage(raw, Decimal(2)).complete
    (raw / "api-usage.jsonl").write_text("malformed", encoding="utf-8")
    usage = campaign.partial_usage(raw, Decimal(2))
    assert not usage.complete
    assert usage.reserved_cost_usd == Decimal(2)
    assert usage.missing_reason == "journal_unreadable"


def bind_preparation(prepared: PreparedCampaign, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        campaign_setup, "verify_protocol", lambda *_: (prepared.configuration, prepared.matrices)
    )
    monkeypatch.setattr(campaign_setup, "require_full_t17", Mock())
    monkeypatch.setattr(campaign_setup, "verify_files", Mock())
    monkeypatch.setattr(campaign_setup, "offline_evidence", lambda *_: {})
    monkeypatch.setattr(
        campaign_setup, "historical_usage", lambda *_: (prepared.plan.historical, ())
    )
    costs = {item.stage: item for item in prepared.plan.stages}
    monkeypatch.setattr(campaign_setup, "stage_cost", lambda root, matrix, *_: costs[matrix.stage])
    monkeypatch.setattr(
        campaign_setup, "claim_path", lambda _: prepared.setup.output.parent / "claim"
    )


def test_preparation_and_exclusive_claim_keep_approval_single_use(
    prepared: PreparedCampaign, monkeypatch: pytest.MonkeyPatch
) -> None:
    bind_preparation(prepared, monkeypatch)
    checked = campaign_setup.prepare_campaign(prepared.setup)
    assert checked == prepared
    assert not prepared.setup.output.exists()
    claim = campaign_setup.claim_campaign(checked)
    assert claim.approval_id == prepared.approval.approval_id
    with pytest.raises(ValueError, match="already_used_keep_partial"):
        campaign_setup.prepare_campaign(prepared.setup)
    with pytest.raises(ExperimentCommandError, match="output_exists"):
        campaign_setup.claim_campaign(checked)


@pytest.mark.parametrize(
    "drift", ["output", "approval", "protocol", "configuration", "readiness", "projection"]
)
def test_preparation_rejects_each_binding_drift(
    prepared: PreparedCampaign, drift: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    bind_preparation(prepared, monkeypatch)
    if drift == "output":
        prepared.setup.output.mkdir()
    elif drift == "approval":
        changed = prepared.approval.model_copy(update={"cost_plan_sha256": "0" * 64})
        prepared.setup.approval.write_text(changed.model_dump_json(), encoding="utf-8")
    elif drift == "protocol":
        (prepared.setup.protocol / "protocol-manifest.json").write_text("{}", encoding="utf-8")
    elif drift == "configuration":
        config = prepared.configuration.model_copy(update={"protocol_id": "wrong"})
        monkeypatch.setattr(
            campaign_setup, "verify_protocol", lambda *_: (config, prepared.matrices)
        )
    elif drift == "readiness":
        monkeypatch.setattr(
            campaign_setup,
            "offline_evidence",
            lambda *_: {"unexpected": prepared.plan.protocol_manifest},
        )
    elif drift == "projection":
        changed = prepared.plan.historical.model_copy(update={"observed_responses": 99})
        monkeypatch.setattr(campaign_setup, "historical_usage", lambda *_: (changed, ()))
    with pytest.raises(ValueError, match="v2_"):
        campaign_setup.prepare_campaign(prepared.setup)


def test_canonical_claim_path_uses_stable_approval_identity(prepared: PreparedCampaign) -> None:
    original = campaign_setup.claim_path(prepared)
    changed = replace(prepared, approval_sha256="f" * 64)
    assert campaign_setup.claim_path(changed) == original
    assert original.parent == prepared.setup.root / "runs/t17-v2-budget-claims"
