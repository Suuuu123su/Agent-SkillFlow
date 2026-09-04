"""T18 独立类型格式接入统一漂移检查，不改旧实验格式。"""

import json
from pathlib import Path

from pydantic import JsonValue

from skillflow.defense.models import (
    AttackDiagnosis,
    AttackSignalVector,
    DefenseOutcome,
    DefensePlan,
)
from skillflow.defense.provider import DefenseTrace
from skillflow.experiment.t18.catalog_models import LocalCatalog
from skillflow.experiment.t18.controls import CellContract
from skillflow.experiment.t18.dataset import DatasetManifest
from skillflow.experiment.t18.hiaa import HiaaReport
from skillflow.experiment.t18.matrix import LocalMatrix
from skillflow.experiment.t18.metric_models import Measure
from skillflow.experiment.t18.preregistration import Preregistration
from skillflow.experiment.t18.replay import LocalReplay
from skillflow.experiment.t18.reporting import LocalReport
from skillflow.experiment.t18.run_models import LocalCore, LocalPhase
from skillflow.experiment.t18.table_models import DiagnosisRow, OutcomeRow, PlanRow, TableManifest


def t18_schema_documents() -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    """返回全部运行、诊断、四格、报告与公开集合格式。"""
    return tuple(
        ("t18-" + name + ".schema.json", model.model_json_schema())
        for name, model in (
            ("matrix", LocalMatrix),
            ("catalog", LocalCatalog),
            ("preregistration", Preregistration),
            ("cell-contract", CellContract),
            ("attack-signals", AttackSignalVector),
            ("attack-diagnosis", AttackDiagnosis),
            ("defense-plan", DefensePlan),
            ("defense-outcome", DefenseOutcome),
            ("defense-trace", DefenseTrace),
            ("hiaa-report", HiaaReport),
            ("phase", LocalPhase),
            ("core", LocalCore),
            ("replay", LocalReplay),
            ("measure", Measure),
            ("report", LocalReport),
            ("dataset-manifest", DatasetManifest),
            ("diagnosis-row", DiagnosisRow),
            ("plan-row", PlanRow),
            ("outcome-row", OutcomeRow),
            ("table-manifest", TableManifest),
        )
    )


def write_t18_schemas(directory: Path) -> None:
    """仅新增 T18 格式；相同内容可复用，不覆盖旧版漂移。"""
    directory.mkdir(parents=True, exist_ok=True)
    for name, document in t18_schema_documents():
        path = directory / name
        text = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise ValueError("t18_static_schema_drift:" + name)
        else:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
