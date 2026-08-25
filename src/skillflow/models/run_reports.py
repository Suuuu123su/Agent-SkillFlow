"""单次 Run 的标准结果契约。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import Decision, EnforcementMode, ProvenanceMode
from skillflow.models.matrix_axes import (
    AuthorizationCondition,
    MatrixRunRole,
    SessionCondition,
    SkillStateCondition,
)
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.metrics import (
    EffectPathEvidence,
    ProvenanceMetricSummary,
    UeaMetricSummary,
    UnauthorizedEffectEvidence,
)
from skillflow.models.references import ScenarioPath
from skillflow.models.run_results import (
    ArtifactAliasEvidence,
    RunEffectResult,
    RunRevocationEvidence,
)
from skillflow.models.scenario_parts import EffectSelector

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


class RunRiskReport(StrictModel):
    """单次 Run 的结果与可审计证据索引。"""

    schema_version: NonEmptyStr
    report_scope: Literal["run"]
    run_id: NonEmptyStr
    scenario_id: NonEmptyStr
    experiment_id: NonEmptyStr | None = None
    scenario: ScenarioPath | None = None
    variant: NonEmptyStr | None = None
    seed: int | None = None
    backend: NonEmptyStr | None = None
    task_success: bool | None = None
    harm: bool | None = None
    uea: UeaMetricSummary
    provenance: ProvenanceMetricSummary
    unauthorized_effects: tuple[UnauthorizedEffectEvidence, ...]
    latency_ms: NonNegativeFloat | None = None
    effect_ids: tuple[NonEmptyStr, ...] = ()
    authorized_flags: tuple[bool, ...] = ()
    baseline_decisions: tuple[Decision, ...] = ()
    policy_decisions: tuple[Decision, ...] = ()
    executed_decisions: tuple[bool, ...] = ()
    receipt_ids: tuple[NonEmptyStr, ...] = ()
    evidence_event_ids: tuple[NonEmptyStr, ...] = ()
    source_to_sink_paths: tuple[EffectPathEvidence, ...] = ()
    effects: tuple[RunEffectResult, ...] = ()
    counterfactual_artifacts: tuple[ArtifactAliasEvidence, ...] = ()
    revocations: tuple[RunRevocationEvidence, ...] = ()
    rir_check_offsets: tuple[NonNegativeInt, ...] = ()
    harm_selector: EffectSelector | None = None
    harm_effect_ids: tuple[NonEmptyStr, ...] = ()
    harm_receipt_ids: tuple[NonEmptyStr, ...] = ()
    hiaa_cell: HiaaCell | None = None
    hiaa_design_id: NonEmptyStr | None = None
    pair_id: NonEmptyStr | None = None
    run_role: MatrixRunRole = MatrixRunRole.CORE
    skill_state: SkillStateCondition = SkillStateCondition.NORMAL
    session_condition: SessionCondition = SessionCondition.ORIGINAL
    authorization_condition: AuthorizationCondition = AuthorizationCondition.NONE
    shared_context: bool | None = None
    persistent_memory: bool | None = None
    auto_approve_tools: bool | None = None
    enforcement_mode: EnforcementMode | None = None
    provenance_mode: ProvenanceMode | None = None
    implicit_text_authorization: bool | None = None
    redacted: bool = True

    @model_validator(mode="after")
    def require_standard_result_alignment(self) -> Self:
        """顶层最低字段必须与结构化 Effect 结果逐项对齐。"""
        if self.effects:
            aligned = (
                self.effect_ids == tuple(item.effect_id for item in self.effects)
                and self.authorized_flags == tuple(item.authorized for item in self.effects)
                and self.baseline_decisions == tuple(item.baseline_result for item in self.effects)
                and self.policy_decisions == tuple(item.policy_result for item in self.effects)
                and self.executed_decisions == tuple(item.executed for item in self.effects)
                and self.receipt_ids == tuple(item.receipt_id for item in self.effects)
            )
            if not aligned:
                raise PydanticCustomError(
                    "run_result_effect_alignment",
                    "RunResult 顶层 Effect/Decision/Receipt 字段必须逐项对齐",
                )
        if len(self.harm_effect_ids) != len(self.harm_receipt_ids):
            raise PydanticCustomError(
                "run_result_harm_receipt_alignment",
                "每个 harm Effect 必须有同 Run Receipt",
            )
        if self.harm is not None and self.harm is not bool(self.harm_effect_ids):
            raise PydanticCustomError(
                "run_result_harm_mismatch",
                "harm 必须等于是否存在 selector 匹配的 Receipt Effect",
            )
        return self
