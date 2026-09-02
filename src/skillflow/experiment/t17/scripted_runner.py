"""T17-D Scripted Matrix 执行与 Golden 汇总编排。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.io import write_json_model
from skillflow.experiment.matrix import MatrixExecutionRequest, execute_matrix
from skillflow.experiment.t17.run_observer import T17RunObservationWriter
from skillflow.experiment.t17.scenario_registry import (
    load_scenario_measurement_registry,
)
from skillflow.experiment.t17.scripted_golden import (
    build_scripted_golden_summary,
    load_scripted_golden_specification,
)
from skillflow.experiment.t17.scripted_models import T17ScriptedGoldenSummary
from skillflow.models.execution import ExperimentKind
from skillflow.models.matrix import ExperimentMatrix
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class T17ScriptedRunRequest:
    """T17-D 的 Matrix、注册表、Golden 与独占输出路径。"""

    matrix_path: Path
    registry_path: Path
    golden_path: Path
    output_root: Path
    summary_output: Path


@dataclass(frozen=True, slots=True)
class T17ScriptedRunOutcome:
    """Scripted 执行目录与已通过 Golden 的汇总。"""

    output_root: Path
    summary_output: Path
    summary: T17ScriptedGoldenSummary


def execute_t17_scripted(request: T17ScriptedRunRequest) -> T17ScriptedRunOutcome:
    """复用 T13 Matrix 全链路并追加 T17 Golden 阶段门。"""
    matrix = validate_yaml_document(request.matrix_path, ExperimentMatrix)
    registry = load_scenario_measurement_registry(request.registry_path)
    observer = T17RunObservationWriter(registry)
    execute_matrix(
        MatrixExecutionRequest(
            matrix_path=request.matrix_path,
            matrix=matrix,
            output=request.output_root,
            determinism_repeats=5,
            redacted=True,
            kind=ExperimentKind.MATRIX,
            source=request.matrix_path.as_posix(),
            run_observer=observer,
        )
    )
    golden = load_scripted_golden_specification(request.golden_path)
    summary = build_scripted_golden_summary(request.output_root, registry, golden)
    request.summary_output.parent.mkdir(parents=True, exist_ok=True)
    write_json_model(request.summary_output, summary)
    return T17ScriptedRunOutcome(
        output_root=request.output_root,
        summary_output=request.summary_output,
        summary=summary,
    )
