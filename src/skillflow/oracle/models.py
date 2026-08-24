"""Oracle 输入证据、运行计划与 JSONL 输出模型。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeAlias

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.manifest import SkillManifest
from skillflow.models.scenario import Scenario
from skillflow.models.tool_calls import MockToolName, ToolArguments
from skillflow.trace.contracts import TraceParent, TraceValueType


@dataclass(frozen=True, slots=True)
class OracleActionPlan:
    """从 ScriptedBackend 动作单向投影出的真值计划。"""

    action_id: str
    arguments: ToolArguments


@dataclass(frozen=True, slots=True)
class OracleSkillPlan:
    """一个 Skill 的稳定脚本动作序列。"""

    skill_id: str
    actions: tuple[OracleActionPlan, ...]


@dataclass(frozen=True, slots=True)
class OracleManifestPlan:
    """已校验 Manifest 与 Skill 主体的绑定。"""

    skill_id: str
    manifest: SkillManifest


@dataclass(frozen=True, slots=True)
class OracleRunPlan:
    """Oracle 启动前冻结的全部声明式输入。"""

    run_id: str
    scenario: Scenario
    skills: tuple[OracleSkillPlan, ...]
    manifests: tuple[OracleManifestPlan, ...]


@dataclass(frozen=True, slots=True)
class OracleReceiptEvidence:
    """Runner 从强类型 Receipt 提取的最小效果证据。"""

    action_id: str
    receipt_id: str
    effect_id: str
    actor_id: str
    call_id: str
    timestamp: datetime
    tool: MockToolName
    argument_artifact_id: str
    receipt_artifact_id: str
    output_artifact_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OracleAttemptEvidence:
    """包括 deny 在内的 Tool argument 稳定 ID 证据。"""

    action_id: str
    actor_id: str
    call_id: str
    tool: MockToolName
    argument_artifact_id: str
    executed: bool


@dataclass(frozen=True, slots=True)
class OracleInvocationEvidence:
    """一次 Scripted Skill 调用的稳定 ID 绑定。"""

    step_id: str
    skill_id: str
    session_id: str
    call_id: str
    input_artifact_ids: tuple[str, ...]
    output_artifact_id: str
    output_aliases: tuple[str, ...]
    attempts: tuple[OracleAttemptEvidence, ...]
    receipts: tuple[OracleReceiptEvidence, ...]


class OracleArtifactTrace(StrictModel):
    """Oracle Plane 中一个值的独立 GT_data。"""

    plane: Literal["oracle"] = "oracle"
    record_type: Literal["artifact"] = "artifact"
    run_id: NonEmptyStr
    artifact_id: NonEmptyStr
    value_type: TraceValueType
    aliases: tuple[NonEmptyStr, ...] = ()
    gt_data: tuple[NonEmptyStr, ...]
    parents: tuple[TraceParent, ...]


class OracleEffectTrace(StrictModel):
    """Receipt 锚定的 GT_effect 与独立 GT_auth。"""

    plane: Literal["oracle"] = "oracle"
    record_type: Literal["effect"] = "effect"
    run_id: NonEmptyStr
    effect_id: NonEmptyStr
    action_id: NonEmptyStr
    actor_id: NonEmptyStr
    task_id: NonEmptyStr
    session_id: NonEmptyStr
    call_id: NonEmptyStr
    timestamp: datetime
    effect: CapabilityEffect
    gt_data: tuple[NonEmptyStr, ...]
    gt_auth: bool
    gt_effect: bool
    manifest_declared: bool
    matched_grant_ids: tuple[NonEmptyStr, ...]
    receipt_id: NonEmptyStr
    parents: tuple[TraceParent, ...]


OracleTraceRecord: TypeAlias = OracleArtifactTrace | OracleEffectTrace
