"""工具执行前已冻结的任务计划、约束和成对归因输入。"""

from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.defense.models import AttackSignalVector, DefenseAction
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect


class TaskNode(StrictModel):
    """精确主体、会话、资源与参数类型；工具返回不能新增节点。"""

    node_id: NonEmptyStr
    actor_id: NonEmptyStr
    session_id: NonEmptyStr
    effect: CapabilityEffect
    predecessor_ids: tuple[NonEmptyStr, ...]
    parameter_schema_id: Literal[
        "read_file", "write_memory", "read_memory", "http_send", "shell_exec"
    ]


class TrustedTaskPlan(StrictModel):
    """从可信任务依赖生成的有向无环工具计划，不包含攻击类别。"""

    schema_version: Literal["18.0"] = "18.0"
    plan_id: NonEmptyStr
    issuer: Literal["trusted_policy"] = "trusted_policy"
    compiled_before_untrusted_input: Literal[True] = True
    nodes: tuple[TaskNode, ...]

    @model_validator(mode="after")
    def validate_dag(self) -> Self:
        """只接受先出现的前置节点，因此无法注入环路或未登记节点。"""
        seen: set[str] = set()
        for node in self.nodes:
            if node.node_id in seen or not set(node.predecessor_ids) <= seen:
                raise ValueError("t18_invalid_task_dependency")
            seen.add(node.node_id)
        return self


class CausalAssessment(StrictModel):
    """由真实隔离重放形成的结果；未评估时不允许带数值。"""

    status: Literal["measured", "not_applicable", "not_available", "incomplete"]
    reason: NonEmptyStr
    pair_id: NonEmptyStr | None = None
    y_original: bool | None = None
    y_neutral: bool | None = None
    ci: Literal[-1, 0, 1] | None = None
    evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_difference(self) -> Self:
        """差值只来自两个分支的有回执效果，不能事后填零。"""
        if self.status == "measured":
            if self.pair_id is None or self.y_original is None or self.y_neutral is None:
                raise ValueError("t18_causal_pair_missing")
            if self.ci != int(self.y_original) - int(self.y_neutral) or not self.evidence_ids:
                raise ValueError("t18_causal_difference_mismatch")
        elif self.ci is not None or self.y_original is not None or self.y_neutral is not None:
            raise ValueError("t18_unmeasured_causal_value")
        return self


class GateResult(StrictModel):
    """一个组件的实际判断及执行开销。"""

    action: DefenseAction
    reason: NonEmptyStr
    evidence_ids: tuple[NonEmptyStr, ...]
    extra_steps: Annotated[int, Field(ge=0)] = 1
    abstain: bool = False


@dataclass(frozen=True, slots=True)
class GateRequest:
    """规范化后的请求；所有身份与授权由可信运行环境传入。"""

    effect: CapabilityEffect
    actor_id: str
    session_id: str
    task_plan: TrustedTaskPlan
    signals: AttackSignalVector
    completed_node_ids: frozenset[str]
    authorized: bool
    base_executed: bool
    memory_key: str | None = None
    memory_operation: Literal["read", "write"] | None = None
    memory_untrusted: bool = False
    memory_artifact_ids: tuple[str, ...] = ()


def matching_nodes(request: GateRequest) -> tuple[TaskNode, ...]:
    """参数已通过工具类型校验，再检查精确效果和执行边界。"""
    return tuple(
        node
        for node in request.task_plan.nodes
        if (
            node.actor_id == request.actor_id
            and node.session_id == request.session_id
            and node.effect == request.effect
        )
    )
