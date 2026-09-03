"""T17 最小域静态 Schema 的唯一机械来源；不重定义历史 Schema。"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import JsonValue, TypeAdapter

from skillflow.benchmark.replay_models import ReplayPairManifest
from skillflow.experiment.t17.minimal.contracts import MinimalConfiguration, NormalTaskContract
from skillflow.experiment.t17.minimal.report_models import MinimalDomainReport, MinimalMeasurement
from skillflow.experiment.t17.minimal.run_models import (
    MinimalExecutionStatus,
    MinimalPhaseContract,
    MinimalRunRecord,
    RawManifest,
)
from skillflow.experiment.t17.minimal.task_models import NormalTaskEvidence
from skillflow.graph.models import SecurityGraphExport
from skillflow.instrumentation.tool_receipt import ToolReceiptDraft
from skillflow.models.base import StrictModel
from skillflow.models.reports import ReplayRiskReport, RunRiskReport
from skillflow.oracle.models import OracleTraceRecord
from skillflow.trace.observed import ObservedTraceRecord

_MODELS: tuple[tuple[str, type[StrictModel]], ...] = (
    ("configuration", MinimalConfiguration),
    ("normal-task-contract", NormalTaskContract),
    ("normal-task-evidence", NormalTaskEvidence),
    ("phase-contract", MinimalPhaseContract),
    ("run-record", MinimalRunRecord),
    ("raw-manifest", RawManifest),
    ("execution-status", MinimalExecutionStatus),
    ("measurement", MinimalMeasurement),
    ("domain-report", MinimalDomainReport),
    ("graph", SecurityGraphExport),
    ("replay-pair", ReplayPairManifest),
    ("run-risk", RunRiskReport),
    ("replay-risk", ReplayRiskReport),
)


def minimal_schema_documents() -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    """新文件名包含 minimal，旧 T09-T17 v1 Schema 保持原样。"""
    documents = tuple((schema_filename(name), model.model_json_schema()) for name, model in _MODELS)
    return (
        *documents,
        (schema_filename("observed-trace"), TypeAdapter(ObservedTraceRecord).json_schema()),
        (schema_filename("oracle-trace"), TypeAdapter(OracleTraceRecord).json_schema()),
        (schema_filename("tool-receipt"), TypeAdapter(ToolReceiptDraft).json_schema()),
    )


def schema_filename(name: str) -> str:
    """稳定、独立的静态文件名。"""
    return "t17-minimal-" + name + ".schema.json"


def static_model_validator(model: type[StrictModel]) -> Draft202012Validator:
    """Raw 读取必须通过已提交静态 Schema，不只验证序列化后的模型。"""
    name = next(name for name, candidate in _MODELS if candidate is model)
    return static_validator(model.model_json_schema(), schema_filename(name))


def static_validator(generated: dict[str, JsonValue], filename: str) -> Draft202012Validator:
    """静态文件与当前类型不一致时拒绝报告，不静默重新生成。"""
    document = json.loads((Path("schemas") / filename).read_text(encoding="utf-8"))
    if document != generated:
        raise ValueError("minimal_static_schema_drift")
    return Draft202012Validator(document)


def write_minimal_schemas(directory: Path) -> None:
    """只独占创建新 minimal Schema；不接触任何旧文件。"""
    documents = minimal_schema_documents()
    if any((directory / name).exists() for name, _ in documents):
        raise ValueError("minimal_static_schema_already_exists")
    directory.mkdir(parents=True, exist_ok=True)
    for name, document in documents:
        with (directory / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
