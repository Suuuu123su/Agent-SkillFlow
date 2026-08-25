"""T13 输入引用、ID 与 Matrix override 的纯转换。"""

import re
from pathlib import Path

from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.models.enums import CapabilityAction, EnforcementMode
from skillflow.models.matrix import ExperimentVariant
from skillflow.models.matrix_axes import AuthorizationCondition
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.references import ScenarioPath
from skillflow.models.resources import ResourceRef
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import EffectSelector, StepAction


def scenario_reference(path: Path) -> ScenarioPath:
    """把本机路径压缩为受控的 scenarios/ 相对引用。"""
    resolved = path.resolve()
    indexes = tuple(index for index, part in enumerate(resolved.parts) if part == "scenarios")
    if not indexes:
        raise ExperimentCommandError(
            ExperimentErrorCode.INPUT_OUTSIDE_REGISTRY,
            "Scenario 必须位于 scenarios/ 注册目录",
            CommandExitCode.INPUT_INVALID,
        )
    relative = Path(*resolved.parts[indexes[-1] :]).as_posix()
    return ScenarioPath(relative)


def selected_harm_selector(scenario: Scenario) -> EffectSelector:
    """返回声明的 harm selector，或结构化 N/A selector。"""
    if scenario.harm_selector is not None:
        return next(
            selector
            for selector in scenario.effect_selectors
            if selector.alias == scenario.harm_selector.alias
        )
    if scenario.effect_selectors:
        return scenario.effect_selectors[0]
    return EffectSelector(
        alias="not-applicable",
        action=CapabilityAction.FILE_READ,
        source_pattern=None,
        sink_pattern=ResourceRef("mock://not-applicable"),
    )


def authorization_condition(scenario: Scenario) -> AuthorizationCondition:
    """从声明式确认步骤与 Harness 开关推导授权来源轴。"""
    if any(
        step.action is StepAction.USER_CONFIRM
        for session in scenario.sessions
        for step in session.steps
    ):
        return AuthorizationCondition.STRUCTURED_CONFIRMATION
    if scenario.harness.implicit_text_authorization:
        return AuthorizationCondition.IMPLICIT_TEXT
    return AuthorizationCondition.NONE


def apply_variant(scenario: Scenario, variant: ExperimentVariant) -> Scenario:
    """只覆盖 Matrix 预注册的 Harness 与 enforcement 轴。"""
    harness = scenario.harness.model_copy(
        update={
            "shared_context": variant.shared_context,
            "persistent_memory": variant.persistent_memory,
            "auto_approve_tools": variant.auto_approve_tools,
            "provenance_mode": variant.provenance_mode,
            "implicit_text_authorization": variant.implicit_text_authorization,
        }
    )
    execution = scenario.execution.model_copy(update={"mode": variant.enforcement_mode})
    oracle = scenario.oracle
    if variant.hiaa_cell is not None and variant.hiaa_cell is not HiaaCell.P11:
        selector_alias = None if variant.harm_selector is None else variant.harm_selector.alias
        oracle = oracle.model_copy(
            update={
                "expected_origins": tuple(
                    expectation
                    for expectation in oracle.expected_origins
                    if expectation.target.root != f"effect-selector:{selector_alias}"
                )
            }
        )
    if variant.enforcement_mode is EnforcementMode.ENFORCE:
        oracle = oracle.model_copy(update={"expected_origins": ()})
    return scenario.model_copy(
        update={"harness": harness, "execution": execution, "oracle": oracle}
    )


def namespace_grants(scenario: Scenario, run_id: str) -> Scenario:
    """在共享 SQLite 中把声明式 Grant ID 限定到当前 Run。"""
    grants = tuple(
        grant.model_copy(update={"grant_id": f"{run_id}-{grant.grant_id}"})
        for grant in scenario.grants
    )
    sessions = tuple(
        session.model_copy(
            update={
                "steps": tuple(
                    step
                    if step.grant is None
                    else step.model_copy(
                        update={
                            "grant": step.grant.model_copy(
                                update={"grant_id": f"{run_id}-{step.grant.grant_id}"}
                            )
                        }
                    )
                    for step in session.steps
                )
            }
        )
        for session in scenario.sessions
    )
    return scenario.model_copy(update={"grants": grants, "sessions": sessions})


def safe_output_id(output: Path) -> str:
    """把输出目录名验证为稳定 Experiment ID。"""
    identifier = output.name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", identifier):
        raise ExperimentCommandError(
            ExperimentErrorCode.INPUT_VALUE_INVALID,
            "输出目录名必须是安全的 Experiment ID",
            CommandExitCode.INPUT_INVALID,
        )
    return identifier


def slug(value: str) -> str:
    """把受控名称压缩为安全小写 ID 片段。"""
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return normalized.lower() or "scenario"
