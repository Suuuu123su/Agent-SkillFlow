"""从类型化模型生成静态 JSON Schema 的唯一入口。"""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.dry_run_reports import T16BDryRunSummary
from skillflow.experiment.t16.live_canary_usage_models import CanaryUsageJournalEvent
from skillflow.experiment.t16.live_config import T16CLiveConfig, T16ELiveConfig
from skillflow.experiment.t16.live_metric_models import LiveMetricsReport
from skillflow.experiment.t16.live_reanalysis_models import LiveReanalysisReport
from skillflow.experiment.t16.live_reanalysis_v3_models import LiveReanalysisReportV3
from skillflow.experiment.t16.live_reanalysis_v4_models import LiveReanalysisReportV4
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.live_run_models import LivePhaseSummary
from skillflow.experiment.t16.live_usage_store import LiveUsageJournalEvent
from skillflow.experiment.t16.provider import ProviderConfig
from skillflow.experiment.t16.t16e_models import T16ECrossModelComparison
from skillflow.experiment.t16.task_success_canary_models import T16D2CanaryRunSummary
from skillflow.experiment.t16.task_success_evidence import (
    TaskSuccessEvidence,
    TaskSuccessResult,
)
from skillflow.experiment.t16.task_success_live_models import (
    T16D2Checkpoint,
    T16D2PreflightManifest,
    T16D2RawTrialRecord,
    T16D2RunSummary,
    T16D2StageGate,
)
from skillflow.experiment.t16.task_success_live_report_models import T16D2BridgeReport
from skillflow.experiment.t16.task_success_matrix import TaskSuccessSmokeMatrix
from skillflow.experiment.t16.task_success_output import StructuredTaskResultV3
from skillflow.experiment.t16.task_success_prereg_models import (
    TaskSuccessPreregistrationV3,
)
from skillflow.experiment.t16.task_success_spec_models import (
    TaskSuccessSpecificationRegistry,
)
from skillflow.experiment.t16.task_success_statistics_models import (
    T16D1PartialReanalysis,
)
from skillflow.experiment.t16.trial import TrialResult
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
from skillflow.experiment.t17.minimal.schema_models import minimal_schema_documents
from skillflow.experiment.t17.observations import ReferenceObservationSnapshot
from skillflow.experiment.t17.scenario_registry import T17ScenarioMeasurementRegistry
from skillflow.experiment.t17.scripted_models import (
    ScriptedGoldenSpecification,
    T17ScriptedGoldenSummary,
)
from skillflow.experiment.t17.task_evidence import T17TaskSuccessEvidence
from skillflow.experiment.t17.v2.schema_models import v2_schema_documents
from skillflow.models.manifest import SkillManifest
from skillflow.models.matrix import ExperimentMatrix
from skillflow.models.reports import RISK_REPORT_ADAPTER
from skillflow.models.scenario import Scenario

JsonSchema = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class SchemaDocument:
    """静态 Schema 文件名及其模型生成内容。"""

    filename: str
    content: JsonSchema


def schema_documents() -> tuple[SchemaDocument, ...]:
    """按固定顺序返回基础与 T16 实验 JSON Schema。"""
    return (
        SchemaDocument("skill-manifest.schema.json", SkillManifest.model_json_schema()),
        SchemaDocument("scenario.schema.json", Scenario.model_json_schema()),
        SchemaDocument(
            "experiment-matrix.schema.json",
            ExperimentMatrix.model_json_schema(),
        ),
        SchemaDocument("risk-report.schema.json", RISK_REPORT_ADAPTER.json_schema()),
        SchemaDocument("t16-trial-result.schema.json", TrialResult.model_json_schema()),
        SchemaDocument("t16-budget.schema.json", BudgetConfig.model_json_schema()),
        SchemaDocument("t16-provider.schema.json", ProviderConfig.model_json_schema()),
        SchemaDocument("t16b-dry-run-summary.schema.json", T16BDryRunSummary.model_json_schema()),
        SchemaDocument("t16c-live-config.schema.json", T16CLiveConfig.model_json_schema()),
        SchemaDocument("t16e-live-config.schema.json", T16ELiveConfig.model_json_schema()),
        SchemaDocument("t16c-live-trial-record.schema.json", LiveTrialRecord.model_json_schema()),
        SchemaDocument("t16c-live-phase-summary.schema.json", LivePhaseSummary.model_json_schema()),
        SchemaDocument("t16c-live-metrics.schema.json", LiveMetricsReport.model_json_schema()),
        SchemaDocument(
            "t16c-live-reanalysis.schema.json",
            LiveReanalysisReport.model_json_schema(),
        ),
        SchemaDocument(
            "t16c-live-reanalysis-v0.3.schema.json",
            LiveReanalysisReportV3.model_json_schema(),
        ),
        SchemaDocument(
            "t16c-live-reanalysis-v0.4.schema.json",
            LiveReanalysisReportV4.model_json_schema(),
        ),
        SchemaDocument(
            "t16-task-success-evidence.schema.json",
            TaskSuccessEvidence.model_json_schema(),
        ),
        SchemaDocument(
            "t16-task-success-result.schema.json",
            TaskSuccessResult.model_json_schema(),
        ),
        SchemaDocument(
            "t16-task-result-v3.schema.json", StructuredTaskResultV3.model_json_schema()
        ),
        SchemaDocument(
            "t16-task-success-specifications-v3.schema.json",
            TaskSuccessSpecificationRegistry.model_json_schema(),
        ),
        SchemaDocument(
            "t16-task-success-preregistration-v3.schema.json",
            TaskSuccessPreregistrationV3.model_json_schema(),
        ),
        SchemaDocument(
            "t16-task-success-smoke-matrix-v3.schema.json",
            TaskSuccessSmokeMatrix.model_json_schema(),
        ),
        SchemaDocument(
            "t16c-v2-partial-reanalysis-v0.5.schema.json",
            T16D1PartialReanalysis.model_json_schema(),
        ),
        SchemaDocument(
            "t16d2-raw-trial-record.schema.json",
            T16D2RawTrialRecord.model_json_schema(),
        ),
        SchemaDocument(
            "t16d2-preflight.schema.json",
            T16D2PreflightManifest.model_json_schema(),
        ),
        SchemaDocument(
            "t16d2-stage-gate.schema.json",
            T16D2StageGate.model_json_schema(),
        ),
        SchemaDocument(
            "t16d2-checkpoint.schema.json",
            T16D2Checkpoint.model_json_schema(),
        ),
        SchemaDocument(
            "t16d2-run-summary.schema.json",
            T16D2RunSummary.model_json_schema(),
        ),
        SchemaDocument(
            "t16d2r-usage-event.schema.json",
            LiveUsageJournalEvent.model_json_schema(),
        ),
        SchemaDocument(
            "t16d2-v31-canary-usage-event.schema.json",
            CanaryUsageJournalEvent.model_json_schema(),
        ),
        SchemaDocument(
            "t16d2-v31-canary-run-summary.schema.json",
            T16D2CanaryRunSummary.model_json_schema(),
        ),
        SchemaDocument(
            "t16d2-bridge-report.schema.json",
            T16D2BridgeReport.model_json_schema(),
        ),
        SchemaDocument(
            "t16e-cross-model-comparison.schema.json",
            T16ECrossModelComparison.model_json_schema(),
        ),
        SchemaDocument(
            "t17-baseline-audit.schema.json",
            T17BaselineAudit.model_json_schema(),
        ),
        SchemaDocument(
            "t17-evidence-domain.schema.json",
            EvidenceDomain.model_json_schema(),
        ),
        SchemaDocument(
            "t17-hook-capability.schema.json",
            HookCapability.model_json_schema(),
        ),
        SchemaDocument(
            "t17-ratio-measurement.schema.json",
            RatioMeasurement.model_json_schema(),
        ),
        SchemaDocument(
            "t17-reference-observations.schema.json",
            ReferenceObservationSnapshot.model_json_schema(),
        ),
        SchemaDocument(
            "t17-scenario-measurements.schema.json",
            T17ScenarioMeasurementRegistry.model_json_schema(),
        ),
        SchemaDocument(
            "t17-scripted-golden.schema.json",
            ScriptedGoldenSpecification.model_json_schema(),
        ),
        SchemaDocument(
            "t17-scripted-summary.schema.json",
            T17ScriptedGoldenSummary.model_json_schema(),
        ),
        SchemaDocument(
            "t17-budget-proposal.schema.json",
            T17BudgetProposal.model_json_schema(),
        ),
        SchemaDocument(
            "t17-live-matrix.schema.json",
            T17LiveMatrix.model_json_schema(),
        ),
        SchemaDocument(
            "t17-live-preregistration.schema.json",
            T17LivePreregistration.model_json_schema(),
        ),
        SchemaDocument(
            "t17-approved-live-config.schema.json",
            T17ApprovedLiveConfig.model_json_schema(),
        ),
        SchemaDocument(
            "t17-budget-approval.schema.json",
            T17BudgetApproval.model_json_schema(),
        ),
        SchemaDocument(
            "t17-live-preflight.schema.json",
            T17LivePreflightManifest.model_json_schema(),
        ),
        SchemaDocument(
            "t17-live-unit-record.schema.json",
            T17LiveUnitRecord.model_json_schema(),
        ),
        SchemaDocument(
            "t17-live-stage-summary.schema.json",
            T17LiveStageSummary.model_json_schema(),
        ),
        SchemaDocument(
            "t17-live-journal-event.schema.json",
            T17LiveJournalEvent.model_json_schema(),
        ),
        SchemaDocument(
            "t17-interval-estimate.schema.json",
            T17IntervalEstimate.model_json_schema(),
        ),
        SchemaDocument(
            "t17-phase-metrics.schema.json",
            T17PhaseMetricsReport.model_json_schema(),
        ),
        SchemaDocument(
            "t17-cross-model.schema.json",
            T17CrossModelReport.model_json_schema(),
        ),
        SchemaDocument(
            "t17-defense-report.schema.json",
            T17DefenseReport.model_json_schema(),
        ),
        SchemaDocument(
            "t17-final-metrics.schema.json",
            T17FinalMetricsReport.model_json_schema(),
        ),
        SchemaDocument(
            "t17-task-success-evidence.schema.json",
            T17TaskSuccessEvidence.model_json_schema(),
        ),
        *(SchemaDocument(name, document) for name, document in minimal_schema_documents()),
        *(SchemaDocument(name, document) for name, document in v2_schema_documents()),
    )


def write_static_schemas(directory: Path) -> None:
    """把模型生成的 Schema 确定性写入受控目录。"""
    directory.mkdir(parents=True, exist_ok=True)
    for document in schema_documents():
        content = json.dumps(
            document.content,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        (directory / document.filename).write_text(f"{content}\n", encoding="utf-8")
