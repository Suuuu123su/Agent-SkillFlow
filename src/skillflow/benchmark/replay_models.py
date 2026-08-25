"""T10 成对反事实重放的结果与证据合同。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.adapters.checkpoint import HarnessCheckpoint
from skillflow.benchmark.scenario_execution import ScenarioExecutionSnapshot
from skillflow.instrumentation.artifact_intervention import ArtifactInterventionResult
from skillflow.instrumentation.skill_proxy import SkillStateSnapshot
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import EffectRecord
from skillflow.models.enums import ArtifactType
from skillflow.models.reports import ReplayRiskReport


class ReplayControlEvidence(StrictModel):
    """证明两分支共享运行条件的一组规范化摘要。"""

    seed_hash: NonEmptyStr
    scripts_hash: NonEmptyStr
    decisions_hash: NonEmptyStr
    manifests_hash: NonEmptyStr
    grants_hash: NonEmptyStr
    clock_start: NonEmptyStr
    checkpoint_state_hash: NonEmptyStr
    same_seed: Literal[True] = True
    same_time: Literal[True] = True
    same_tool_returns: Literal[True] = True
    same_other_inputs: Literal[True] = True
    same_permissions: Literal[True] = True
    same_tool_set: Literal[True] = True


class ReplayInterventionEvidence(StrictModel):
    """不包含正文或宿主路径的 Artifact 干预证据。"""

    mode: Literal["identity", "neutral"]
    source_artifact_id: NonEmptyStr
    derived_artifact_id: NonEmptyStr
    artifact_type: ArtifactType
    mime_type: NonEmptyStr
    content_hash: NonEmptyStr
    content_length: Annotated[int, Field(ge=0)]
    schema_preserved: bool


class ReplayPairManifest(StrictModel):
    """一对恢复分支的确定性、隔离性与结构守恒清单。"""

    schema_version: Literal["0.1"] = "0.1"
    replay_id: NonEmptyStr
    target_alias: NonEmptyStr
    checkpoint_id: NonEmptyStr
    checkpoint_prefix_hash: NonEmptyStr
    checkpoint_state_hash: NonEmptyStr
    original_run_id: NonEmptyStr
    neutral_run_id: NonEmptyStr
    original_restore_state_hash: NonEmptyStr
    neutral_restore_state_hash: NonEmptyStr
    original_prefix_hash: NonEmptyStr
    neutral_prefix_hash: NonEmptyStr
    controls: ReplayControlEvidence
    original_intervention: ReplayInterventionEvidence
    neutral_intervention: ReplayInterventionEvidence
    original_effect_ids: tuple[NonEmptyStr, ...]
    neutral_effect_ids: tuple[NonEmptyStr, ...]
    removed_effect_ids: tuple[NonEmptyStr, ...]
    added_effect_ids: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_branch_controls(self) -> Self:
        """拒绝不共享 checkpoint 或破坏 Artifact 结构的配对。"""
        if self.original_run_id == self.neutral_run_id:
            self._invalid("两分支 run_id 必须不同")
        restored = (
            self.original_restore_state_hash,
            self.neutral_restore_state_hash,
            self.controls.checkpoint_state_hash,
        )
        if any(item != self.checkpoint_state_hash for item in restored):
            self._invalid("两分支必须恢复同一个 checkpoint state")
        if (
            self.original_prefix_hash != self.checkpoint_prefix_hash
            or self.neutral_prefix_hash != self.checkpoint_prefix_hash
        ):
            self._invalid("两分支的干预前 Trace 前缀必须一致")
        original = self.original_intervention
        neutral = self.neutral_intervention
        if original.mode != "identity" or neutral.mode != "neutral":
            self._invalid("分支干预必须分别为 identity 与 neutral")
        if original.source_artifact_id != neutral.source_artifact_id:
            self._invalid("两分支必须干预同一源 Artifact")
        structure = (original.artifact_type, original.mime_type, original.content_length)
        neutral_structure = (neutral.artifact_type, neutral.mime_type, neutral.content_length)
        if structure != neutral_structure or not neutral.schema_preserved:
            self._invalid("中和 Artifact 必须保持类型、MIME、长度与 Schema")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("replay_pair_inconsistent", detail)


@dataclass(frozen=True, slots=True)
class ReplaySourceState:
    """目标 Artifact 产生后冻结的公共分支根。"""

    checkpoint: HarnessCheckpoint
    execution: ScenarioExecutionSnapshot
    source_artifact_id: str


@dataclass(frozen=True, slots=True)
class ReplayBranchResult:
    """一个恢复分支完成后的内部强类型事实。"""

    run_id: str
    restore_state_hash: str
    prefix_hash: str
    intervention: ArtifactInterventionResult
    pre_intervention_skill_state: SkillStateSnapshot
    effects: tuple[EffectRecord, ...]
    receipts: tuple[ToolReceipt, ...]


@dataclass(frozen=True, slots=True)
class ReplayPairResult:
    """调用方可复核的一对反事实结果。"""

    target_alias: str
    report: ReplayRiskReport
    report_path: Path
    manifest_path: Path
    checkpoint: HarnessCheckpoint
    original_restore_state_hash: str
    neutral_restore_state_hash: str
    original_prefix_hash: str
    neutral_prefix_hash: str
    original_intervention: ArtifactInterventionResult
    neutral_intervention: ArtifactInterventionResult
    original_pre_intervention_skill_state: SkillStateSnapshot
    neutral_pre_intervention_skill_state: SkillStateSnapshot


@dataclass(frozen=True, slots=True)
class ReplayBatchResult:
    """一个 Scenario 中全部预注册反事实配对。"""

    scenario_id: str
    pairs: tuple[ReplayPairResult, ...]
