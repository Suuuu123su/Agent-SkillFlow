"""从类型化模型生成静态 JSON Schema 的唯一入口。"""

import json
from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.provider import ProviderConfig
from skillflow.experiment.t16.trial import TrialResult
from skillflow.models.manifest import SkillManifest
from skillflow.models.matrix import ExperimentMatrix
from skillflow.models.reports import RISK_REPORT_ADAPTER
from skillflow.models.scenario import Scenario

JsonSchema = dict[str, object]


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
