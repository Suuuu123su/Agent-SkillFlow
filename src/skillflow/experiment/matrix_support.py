"""Matrix 编排共享的强类型运行上下文与报告元数据。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.analysis.facts import RunReportMetadata
from skillflow.benchmark.runner import ScenarioRunResult
from skillflow.models.execution import ExecutionBackend
from skillflow.models.matrix import ExperimentVariant
from skillflow.models.matrix_axes import MatrixRunRole
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import EffectSelector


@dataclass(frozen=True, slots=True)
class ExecutedVariant:
    """一个已执行 Matrix 变体及其稳定输入。"""

    variant: ExperimentVariant
    scenario_path: Path
    scenario: Scenario
    result: ScenarioRunResult


def build_run_metadata(
    experiment_id: str,
    variant: ExperimentVariant,
    selector: EffectSelector | None,
    redacted: bool,
    role: MatrixRunRole = MatrixRunRole.CORE,
) -> RunReportMetadata:
    """生成核心运行与确定性副本共用的标准报告元数据。"""
    return RunReportMetadata(
        experiment_id=experiment_id,
        scenario=variant.scenario,
        variant=variant.variant,
        seed=variant.seed,
        backend=ExecutionBackend.SCRIPTED.value,
        latency_ms=0.0,
        harm_selector=selector,
        hiaa_cell=variant.hiaa_cell,
        hiaa_design_id=variant.hiaa_design_id,
        pair_id=variant.pair_id,
        run_role=role,
        skill_state=variant.skill_state,
        session_condition=variant.session_condition,
        authorization_condition=variant.authorization_condition,
        shared_context=variant.shared_context,
        persistent_memory=variant.persistent_memory,
        auto_approve_tools=variant.auto_approve_tools,
        enforcement_mode=variant.enforcement_mode,
        provenance_mode=variant.provenance_mode,
        implicit_text_authorization=variant.implicit_text_authorization,
        redacted=redacted,
    )
