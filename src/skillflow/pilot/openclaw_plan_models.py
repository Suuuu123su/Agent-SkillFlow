"""Python 与 OpenClaw Driver 之间的严格执行计划模型。"""

from enum import StrEnum, unique
from typing import Annotated, Literal

from pydantic import Field

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import CapabilityAction, Lifetime, Scope
from skillflow.models.resources import ResourceRef

Sensitivity = Annotated[int, Field(ge=0, le=4)]


@unique
class OpenClawToolName(StrEnum):
    """Pilot 唯一允许模型调用的三种工具。"""

    READ = "read"
    WRITE = "write"
    SAFE_SINK = "skillflow_safe_sink"


class OpenClawSkillPlan(StrictModel):
    """隔离 Workspace 中一个最小 Skill。"""

    skill_id: NonEmptyStr


class OpenClawWorkspaceFile(StrictModel):
    """从 Scenario asset 派生的隔离输入文件。"""

    relative_path: NonEmptyStr
    content: NonEmptyStr


class OpenClawResourceFact(StrictModel):
    """观察插件对成功文件或 Memory Tool 的结构化解释。"""

    tool: OpenClawToolName
    relative_path: NonEmptyStr
    resource: ResourceRef
    action: CapabilityAction
    source: ResourceRef | None
    sink: ResourceRef
    scope: Scope
    lifetime: Lifetime = Lifetime.CALL
    sensitivity: Sensitivity
    origin_ids: tuple[NonEmptyStr, ...]
    effect_alias: NonEmptyStr | None = None


class OpenClawToolCall(StrictModel):
    """假模型可输出的封闭 Tool call。"""

    tool: OpenClawToolName
    relative_path: NonEmptyStr | None = None
    content: NonEmptyStr | None = None
    effect_alias: NonEmptyStr | None = None
    action: CapabilityAction | None = None
    source: ResourceRef | None = None
    sink: ResourceRef | None = None
    sensitivity: Sensitivity | None = None
    origin_ids: tuple[NonEmptyStr, ...] = ()


class OpenClawInvocationPlan(StrictModel):
    """一个真实 OpenClaw Agent 回合。"""

    session_id: NonEmptyStr
    step_id: NonEmptyStr
    skill_id: NonEmptyStr
    prompt: NonEmptyStr
    tool_calls: tuple[OpenClawToolCall, ...]


class OpenClawRevocationPlan(StrictModel):
    """Scenario Benchmark 控制面中的撤销事实。"""

    session_id: NonEmptyStr
    skill_id: NonEmptyStr


class OpenClawScenarioPlan(StrictModel):
    """Python 与 OpenClaw Driver 之间的完整请求。"""

    schema_version: Literal["0.1"] = "0.1"
    scenario_id: NonEmptyStr
    task_id: NonEmptyStr
    run_id: NonEmptyStr
    skills: tuple[OpenClawSkillPlan, ...]
    workspace_files: tuple[OpenClawWorkspaceFile, ...]
    resources: tuple[OpenClawResourceFact, ...]
    invocations: tuple[OpenClawInvocationPlan, ...]
    revocations: tuple[OpenClawRevocationPlan, ...]
    target_effect_aliases: tuple[NonEmptyStr, ...]
    expected_origin_ids: tuple[NonEmptyStr, ...]
