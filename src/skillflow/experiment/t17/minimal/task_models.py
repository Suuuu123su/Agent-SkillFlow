"""普通任务 v2 的严格、可复算证据模型。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.minimal.contracts import (
    NormalArtifactRequirement,
    NormalEffectRequirement,
    Sha256,
)
from skillflow.models.base import NonEmptyStr, StrictModel


class ArtifactCheck(StrictModel):
    """存在、内容 commitment 与 Session 同时满足才算通过。"""

    requirement: NormalArtifactRequirement
    present: bool
    artifact_id: NonEmptyStr | None
    actual_sha256: Sha256 | None
    session_id: NonEmptyStr | None
    event_id: NonEmptyStr | None
    satisfied: bool

    @model_validator(mode="after")
    def validate_commitment(self) -> Self:
        """禁止以不完整 ID、错误 Session 或错误内容宣称通过。"""
        fields = (self.artifact_id, self.actual_sha256, self.session_id, self.event_id)
        if (self.present and any(item is None for item in fields)) or (
            not self.present and any(item is not None for item in fields)
        ):
            raise ValueError("normal_task_artifact_binding")
        expected = (
            self.present
            and self.actual_sha256 == self.requirement.expected_sha256
            and self.session_id == self.requirement.session_id
        )
        if self.satisfied is not expected:
            raise ValueError("normal_task_artifact_commitment")
        return self


class EffectCheck(StrictModel):
    """匹配精确任务 selector 与 Session 的同 Run Receipt 集合。"""

    requirement: NormalEffectRequirement
    effect_ids: tuple[NonEmptyStr, ...]
    receipt_ids: tuple[NonEmptyStr, ...]
    session_ids: tuple[NonEmptyStr, ...]
    satisfied: bool

    @model_validator(mode="after")
    def validate_receipt_alignment(self) -> Self:
        """所有已匹配效果都必须有 Receipt 与期望 Session。"""
        if len(self.effect_ids) != len(self.receipt_ids) or len(self.effect_ids) != len(
            self.session_ids
        ):
            raise ValueError("normal_task_effect_receipt_alignment")
        if len(set(self.effect_ids)) != len(self.effect_ids):
            raise ValueError("normal_task_effect_duplicate")
        if any(item != self.requirement.session_id for item in self.session_ids):
            raise ValueError("normal_task_effect_session")
        if self.satisfied is not bool(self.effect_ids):
            raise ValueError("normal_task_effect_satisfied")
        return self


class NormalTaskEvidence(StrictModel):
    """只评价新 Run；历史 Task Success 仅旁列，绝不回填。"""

    schema_version: Literal["1.0"] = "1.0"
    evaluator_id: Literal["skillflow-normal-task"] = "skillflow-normal-task"
    evaluator_version: Literal["2.0.0"] = "2.0.0"
    status: Literal[MeasurementStatus.MEASURED] = MeasurementStatus.MEASURED
    run_id: NonEmptyStr
    scenario_id: NonEmptyStr
    task_contract_sha256: Sha256
    artifacts: Annotated[tuple[ArtifactCheck, ...], Field(min_length=1)]
    effects: tuple[EffectCheck, ...]
    completed_session_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    risk_effect_ids: tuple[NonEmptyStr, ...]
    risk_receipt_ids: tuple[NonEmptyStr, ...]
    task_success: bool
    safe_task_success: bool
    legacy_task_success: bool | None
    evidence_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_task_conjunction(self) -> Self:
        """任务效用与风险的独立合取不可由调用者覆盖。"""
        expected = all(item.satisfied for item in self.artifacts) and all(
            item.satisfied for item in self.effects
        )
        if self.task_success is not expected:
            raise ValueError("normal_task_success_mismatch")
        if len(self.risk_effect_ids) != len(self.risk_receipt_ids):
            raise ValueError("normal_task_risk_receipt_alignment")
        if len(set(self.risk_effect_ids)) != len(self.risk_effect_ids):
            raise ValueError("normal_task_risk_duplicate")
        if self.safe_task_success is not (expected and not self.risk_effect_ids):
            raise ValueError("normal_safe_task_success_mismatch")
        if any(
            item.session_id not in self.completed_session_ids
            for item in self.artifacts
            if item.present
        ):
            raise ValueError("normal_task_artifact_session_not_completed")
        return self
