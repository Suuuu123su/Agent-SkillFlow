import json
from pathlib import Path

from jsonschema import Draft202012Validator

from skillflow.experiment.t17.baseline_audit import T17BaselineAudit
from skillflow.experiment.t17.budget_proposal import T17BudgetProposal
from skillflow.experiment.t17.comparison_models import T17CrossModelReport
from skillflow.experiment.t17.contracts import EvidenceDomain, HookCapability, RatioMeasurement
from skillflow.experiment.t17.defense_models import T17DefenseReport
from skillflow.experiment.t17.final_models import T17FinalMetricsReport
from skillflow.experiment.t17.live_attempt_models import (
    T17BudgetApproval,
    T17LivePreflightManifest,
    T17LiveStageSummary,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_journal_models import T17LiveJournalEvent
from skillflow.experiment.t17.live_matrix import T17LiveMatrix, T17LivePreregistration
from skillflow.experiment.t17.live_reference_client import T17ApprovedLiveConfig
from skillflow.experiment.t17.metric_models import (
    T17IntervalEstimate,
    T17PhaseMetricsReport,
)
from skillflow.experiment.t17.observations import ReferenceObservationSnapshot
from skillflow.experiment.t17.scenario_registry import T17ScenarioMeasurementRegistry
from skillflow.experiment.t17.scripted_models import (
    ScriptedGoldenSpecification,
    T17ScriptedGoldenSummary,
)
from skillflow.experiment.t17.task_evidence import T17TaskSuccessEvidence


def test_t17_static_schemas_match_models() -> None:
    # Given: the four public T17 boundary models and their checked-in schemas.
    documents = {
        "t17-baseline-audit.schema.json": T17BaselineAudit.model_json_schema(),
        "t17-evidence-domain.schema.json": EvidenceDomain.model_json_schema(),
        "t17-hook-capability.schema.json": HookCapability.model_json_schema(),
        "t17-ratio-measurement.schema.json": RatioMeasurement.model_json_schema(),
        "t17-reference-observations.schema.json": (
            ReferenceObservationSnapshot.model_json_schema()
        ),
        "t17-scenario-measurements.schema.json": (
            T17ScenarioMeasurementRegistry.model_json_schema()
        ),
        "t17-scripted-golden.schema.json": ScriptedGoldenSpecification.model_json_schema(),
        "t17-scripted-summary.schema.json": T17ScriptedGoldenSummary.model_json_schema(),
        "t17-budget-proposal.schema.json": T17BudgetProposal.model_json_schema(),
        "t17-live-matrix.schema.json": T17LiveMatrix.model_json_schema(),
        "t17-live-preregistration.schema.json": T17LivePreregistration.model_json_schema(),
        "t17-approved-live-config.schema.json": T17ApprovedLiveConfig.model_json_schema(),
        "t17-budget-approval.schema.json": T17BudgetApproval.model_json_schema(),
        "t17-live-preflight.schema.json": T17LivePreflightManifest.model_json_schema(),
        "t17-live-unit-record.schema.json": T17LiveUnitRecord.model_json_schema(),
        "t17-live-stage-summary.schema.json": T17LiveStageSummary.model_json_schema(),
        "t17-live-journal-event.schema.json": T17LiveJournalEvent.model_json_schema(),
        "t17-interval-estimate.schema.json": T17IntervalEstimate.model_json_schema(),
        "t17-phase-metrics.schema.json": T17PhaseMetricsReport.model_json_schema(),
        "t17-cross-model.schema.json": T17CrossModelReport.model_json_schema(),
        "t17-defense-report.schema.json": T17DefenseReport.model_json_schema(),
        "t17-final-metrics.schema.json": T17FinalMetricsReport.model_json_schema(),
        "t17-task-success-evidence.schema.json": T17TaskSuccessEvidence.model_json_schema(),
    }

    # When/Then: every static document is valid Draft 2020-12 and matches its model.
    for filename, expected in documents.items():
        actual = json.loads((Path("schemas") / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(actual)
        assert actual == expected
