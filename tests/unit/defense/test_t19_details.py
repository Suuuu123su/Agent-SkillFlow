from pathlib import Path

import pytest

from skillflow.experiment.t17.v2.api_models import V2LiveConfig
from skillflow.experiment.t17.v2.canonical import canonical_digest
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t19.accounting import LedgerInputs, recompute_cost
from skillflow.experiment.t19.campaign import CampaignPlan, CampaignSetup, run_campaign
from skillflow.experiment.t19.detail_views import _usage_details, details
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.experiment.t19.formal_plan import formal_plan
from skillflow.experiment.t19.metric_adapter import bind_skill
from skillflow.experiment.t19.public_facts import PublicCore, PublicReplay
from skillflow.experiment.t19.replay import ReplayRecord
from skillflow.experiment.t19.reporting import PublicIndex
from skillflow.experiment.t19.tasks import task_variant
from skillflow.experiment.t19.usage import read_usage

from .test_t19_live import client_for, request

ROOT = Path(__file__).resolve().parents[3]


def test_six_group_common_memory_eligibility_and_strict_views(tmp_path: Path) -> None:
    original = formal_plan()
    block = next(t.block for t in original.trials if t.mechanism == "M2")
    trials = tuple(t for t in original.trials if t.block == block)
    plan = CampaignPlan(
        domain="fake_reference",
        fixed=("T",),
        trials=trials,
        audit_aliases={t.trial_id: original.audit_aliases[t.trial_id] for t in trials},
    )
    run_campaign(CampaignSetup(ROOT, tmp_path, plan, V2FakeClient(), lambda _p: None))
    public = tuple(
        PublicCore.capture(
            t,
            bind_skill(task_variant(ROOT, t.mechanism, t.role, t.template)),
            CoreRecord.model_validate_json(
                (tmp_path / "core" / (t.trial_id + ".json")).read_text(encoding="utf-8")
            ),
        )
        for t in trials
    )
    pairs = tuple(
        PublicReplay.capture(ReplayRecord.model_validate_json(p.read_text(encoding="utf-8")))
        for p in sorted((tmp_path / "audits").glob("*/*.json"))
    )
    config = V2LiveConfig.model_validate_json(
        (ROOT / "experiments/t19/model-reference.json").read_text(encoding="utf-8")
    )
    index = PublicIndex(phase_sha256=canonical_digest("test"), plan=plan)
    result = details(
        index, public, pairs, LedgerInputs(pricing=config.provider.pricing, journals={})
    )
    assert result.common_memory_blocks == (block,)
    assert result.metrics["main/Monitor/M2/common/rir_1"].denominator == 1
    assert result.metrics["main/Monitor/M2/common/rir_1"].value == 0
    altered = public[0].model_copy(
        update={"binding": public[0].binding.model_copy(update={"source_control_hashes": ()})}
    )
    missing = details(
        index,
        (altered, *public[1:]),
        pairs,
        LedgerInputs(pricing=config.provider.pricing, journals={}),
    )
    assert missing.common_memory_blocks == ()
    assert missing.metrics["main/Monitor/M2/common/rir_1"].value is None


def test_token_cost_recompute_accounts_for_registered_recovery(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path)
    client.begin_unit("unit")
    request(client, "same")
    client.record_recovery_intent(("test-argument",), ("blocked-action",))
    request(client, "same")
    ledger = LedgerInputs(
        pricing=client.config.provider.pricing,
        journals={"formal-test": read_usage(tmp_path / "usage.jsonl", tmp_path)},
    )
    report = recompute_cost(ledger)
    assert report.complete
    assert report.api_calls == report.responses == 2
    assert report.estimated_cost_usd == client.unit_usage().estimated_cost_usd


def test_replay_reused_call_id_is_not_a_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = client_for(tmp_path)
    client.begin_unit("core")
    request(client, "shared-call")
    client.begin_unit("core:audit:source:identity")
    original_bind = client.bind_call
    monkeypatch.setattr(
        client,
        "bind_call",
        lambda call: original_bind(call.model_copy(update={"run_id": "branch-run"})),
    )
    request(client, "shared-call")
    client.record_recovery_intent(("blocked-source",), ("blocked-action",))
    request(client, "shared-call")
    ledger = LedgerInputs(
        pricing=client.config.provider.pricing,
        journals={"formal-test": read_usage(tmp_path / "usage.jsonl", tmp_path)},
    )
    recovery, categories, _ = _usage_details(ledger)
    assert len(recovery) == 1
    assert categories["formal/core/initial"]["responses"] == 1
    assert categories["formal/audit/initial"]["responses"] == 1
    assert categories["formal/audit/recovery"]["responses"] == 1
