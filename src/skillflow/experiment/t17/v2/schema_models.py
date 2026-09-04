"""第二版独立静态格式；不会覆盖旧协议的任何格式文件。"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import JsonValue

from skillflow.experiment.t17.v2.api_models import ApiUsageEvent, V2LiveConfig
from skillflow.experiment.t17.v2.campaign_models import (
    CampaignClaim,
    CampaignResult,
    StageBudgetProposal,
    StageOutcome,
    StageProgress,
)
from skillflow.experiment.t17.v2.catalog_models import SkillBundle, SkillCatalog, SkillVariant
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.cost_models import BudgetApproval, CostPlan, StageCost
from skillflow.experiment.t17.v2.csv_models import ComparisonCsvRow, MetricCsvRow
from skillflow.experiment.t17.v2.dataset_models import DatasetManifest, DatasetReports, ReportIndex
from skillflow.experiment.t17.v2.dataset_rows import (
    ApiUsageRow,
    CoreRow,
    EffectReceiptRow,
    HashManifest,
    ProvenanceRow,
    ReplayRow,
    TaskEvidenceRow,
)
from skillflow.experiment.t17.v2.golden_models import GoldenReport, GoldenSpecification
from skillflow.experiment.t17.v2.portable_models import PortableCore, PortableRun
from skillflow.experiment.t17.v2.prompt_contract import PromptContract
from skillflow.experiment.t17.v2.report_models import ComparisonReport, MetricVectorReport
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    PhaseContract,
    PhaseGate,
    ReplayProof,
    ReplayTerminal,
    StageResult,
)
from skillflow.experiment.t17.v2.session_models import (
    CampaignReplacement,
    CommandReceipt,
    InterruptionManifest,
    ResumeCommand,
    SessionCommand,
    SessionCommandReceipt,
)
from skillflow.experiment.t17.v2.statistics_models import Measurement, StatisticalInterval
from skillflow.models.base import StrictModel

_MODELS: tuple[tuple[str, type[StrictModel]], ...] = (
    ("campaign-replacement", CampaignReplacement),
    ("session-command", SessionCommand),
    ("session-command-receipt", SessionCommandReceipt),
    ("resume-command", ResumeCommand),
    ("command-receipt", CommandReceipt),
    ("interruption-manifest", InterruptionManifest),
    ("campaign-claim", CampaignClaim),
    ("campaign-result", CampaignResult),
    ("stage-budget-proposal", StageBudgetProposal),
    ("stage-outcome", StageOutcome),
    ("stage-progress", StageProgress),
    ("cost-plan", CostPlan),
    ("budget-approval", BudgetApproval),
    ("stage-cost", StageCost),
    ("report-index", ReportIndex),
    ("golden-specification", GoldenSpecification),
    ("golden-report", GoldenReport),
    ("configuration", V2Configuration),
    ("matrix", V2Matrix),
    ("skill-catalog", SkillCatalog),
    ("skill-variant", SkillVariant),
    ("skill-bundle", SkillBundle),
    ("prompt", PromptContract),
    ("live-config", V2LiveConfig),
    ("api-usage", ApiUsageEvent),
    ("phase-contract", PhaseContract),
    ("phase-gate", PhaseGate),
    ("core-terminal", CoreTerminal),
    ("replay-terminal", ReplayTerminal),
    ("core-facts", PortableCore),
    ("run-facts", PortableRun),
    ("replay-proof", ReplayProof),
    ("stage-result", StageResult),
    ("measurement", Measurement),
    ("interval", StatisticalInterval),
    ("metric-vector", MetricVectorReport),
    ("comparison", ComparisonReport),
    ("dataset-manifest", DatasetManifest),
    ("dataset-reports", DatasetReports),
    ("core-row", CoreRow),
    ("replay-row", ReplayRow),
    ("task-row", TaskEvidenceRow),
    ("effect-row", EffectReceiptRow),
    ("provenance-row", ProvenanceRow),
    ("api-row", ApiUsageRow),
    ("hash-manifest", HashManifest),
    ("metric-csv", MetricCsvRow),
    ("comparison-csv", ComparisonCsvRow),
)


def v2_schema_documents() -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    """文件名显式区分 v2，全部由类型机械生成。"""
    return tuple(
        ("t17-v2-" + name + ".schema.json", model.model_json_schema()) for name, model in _MODELS
    )


def write_v2_schemas(directory: Path) -> None:
    """只创建尚不存在的 v2 文件，不改写历史格式。"""
    documents = v2_schema_documents()
    if any((directory / name).exists() for name, _ in documents):
        raise ValueError("v2_schema_already_exists")
    directory.mkdir(parents=True, exist_ok=True)
    for name, schema in documents:
        Draft202012Validator.check_schema(schema)
        with (directory / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def verify_v2_schemas(directory: Path) -> None:
    """静态文件和模型不一致就拒绝启动，不在运行时自动改格式。"""
    for name, schema in v2_schema_documents():
        if json.loads((directory / name).read_text(encoding="utf-8")) != schema:
            raise ValueError("v2_static_schema_drift:" + name)
