from pathlib import Path

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t19.accounting import LedgerInputs
from skillflow.experiment.t19.campaign import CampaignPlan
from skillflow.experiment.t19.execution import ExecutionSetup, execute
from skillflow.experiment.t19.matrix import precheck
from skillflow.experiment.t19.operational_views import operational_metrics
from skillflow.experiment.t19.reporting import PublicIndex
from skillflow.experiment.t19.tasks import task_variant
from skillflow.experiment.t19.usage import read_usage

from .test_t19_live import client_for, request

ROOT = Path(__file__).resolve().parents[3]


def test_api_latency_uses_responses_and_missing_core_stays_incomplete(tmp_path: Path) -> None:
    trial = next(t for t in precheck() if t.mechanism == "B0" and t.group == "Monitor")
    core, _ = execute(
        ExecutionSetup(ROOT, tmp_path / "fake-core", trial.trial_id, "fake_reference", trial.group),
        task_variant(ROOT, trial.mechanism, trial.role, trial.template),
        V2FakeClient(),
    )
    client, transport = client_for(tmp_path / "local-transport")
    client.begin_unit(trial.trial_id)
    request(client, "one")
    journal = read_usage(tmp_path / "local-transport/usage.jsonl", tmp_path / "local-transport")
    ledger = LedgerInputs(pricing=client.config.provider.pricing, journals={"test-local": journal})
    plan = CampaignPlan(domain="fake_reference", fixed=("T",), trials=(trial,), audit_aliases={})
    index = PublicIndex(phase_sha256="a" * 64, plan=plan)
    metrics = operational_metrics(index, {trial.trial_id: core}, ledger)
    response = next(e for e in journal if e.event_type == "response")
    assert transport.calls == 1
    assert metrics["main/Monitor/latency.api_ms"].value == response.latency_ms
    assert metrics["main/Monitor/latency.api_ms"].denominator == 1
    assert metrics["main/Monitor/failure_rate/schema_rejection"].denominator == len(core.decisions)
    assert metrics["main/Monitor/failure_rate/schema_rejection"].value == 0
    assert (
        metrics["main/Monitor/latency.exclusive_task_execution_ms"].status
        is MeasurementStatus.NOT_AVAILABLE
    )
    missing = operational_metrics(index, {}, ledger)
    assert (
        missing["main/Monitor/failure_rate/schema_rejection"].status is MeasurementStatus.INCOMPLETE
    )
    assert missing["main/Monitor/latency.api_ms"].value is None
