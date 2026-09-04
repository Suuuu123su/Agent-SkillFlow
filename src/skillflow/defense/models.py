"""T18 诊断与防御数据合同；缺失证据不能变成安全值零。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.models.base import NonEmptyStr, StrictModel

DefenseId = Literal["task-alignment", "tdg", "drift-isolation", "causal"]
Mechanism = Literal["privilege", "context-tool", "memory", "authorization"]
DefenseAction = Literal["allow", "deny", "confirm", "quarantine", "replay_then_decide"]


class AttackSignalVector(StrictModel):
    """一次工具请求的可信事实；模式、文件名与攻击标签均不在输入面。"""

    schema_version: Literal["18.0"] = "18.0"
    run_id: NonEmptyStr
    session_id: NonEmptyStr
    request_event_id: NonEmptyStr
    grant_missing: bool
    scope_mismatch: bool
    lifetime_mismatch: bool
    revoked_origin: bool
    untrusted_context_in_basis: bool
    untrusted_tool_return_in_basis: bool
    cross_session_memory_path: bool
    authorization_claim_in_basis: bool
    candidate_influence: bool
    confirmed_influence: bool
    target_effect_requested: bool
    target_effect_executed: bool
    receipt_present: bool
    sink_severity: Annotated[int, Field(ge=0, le=4)]
    evidence_availability: dict[NonEmptyStr, bool]
    evidence_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    signal_evidence: dict[NonEmptyStr, tuple[NonEmptyStr, ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """结构化证据引用必须封闭；执行与确认影响不能缺少对应事实。"""
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("t18_duplicate_evidence")
        if any(not set(ids) <= set(self.evidence_ids) for ids in self.signal_evidence.values()):
            raise ValueError("t18_signal_evidence_not_bound")
        if self.confirmed_influence and not self.candidate_influence:
            raise ValueError("t18_confirmation_requires_candidate")
        if self.target_effect_executed and not self.receipt_present:
            raise ValueError("t18_executed_requires_receipt")
        return self


class AttackDiagnosis(StrictModel):
    """置信等级是规则的证据充分性，不是假造的概率。"""

    schema_version: Literal["18.0"] = "18.0"
    diagnosis_id: NonEmptyStr
    mechanisms: tuple[Mechanism, ...]
    confidence: Literal["high", "medium", "low"]
    abstain: bool
    evidence_ids: tuple[NonEmptyStr, ...]
    missing_evidence: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_abstention(self) -> Self:
        """缺少必要证据时明确放弃确定诊断。"""
        if len(set(self.mechanisms)) != len(self.mechanisms):
            raise ValueError("t18_duplicate_mechanism")
        if bool(self.missing_evidence) != self.abstain:
            raise ValueError("t18_abstention_evidence_mismatch")
        if self.abstain and self.confidence != "low":
            raise ValueError("t18_abstention_confidence")
        return self


class DefensePlan(StrictModel):
    """防御选择只可收紧执行，不签发或修改授权。"""

    schema_version: Literal["18.0"] = "18.0"
    plan_id: NonEmptyStr
    selected_defense_ids: tuple[DefenseId, ...]
    action: DefenseAction
    evidence_ids: tuple[NonEmptyStr, ...]
    selection_reason_codes: tuple[NonEmptyStr, ...]
    estimated_extra_steps: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_union(self) -> Self:
        """混合机制的选择是去重集合。"""
        if len(set(self.selected_defense_ids)) != len(self.selected_defense_ids):
            raise ValueError("t18_duplicate_defense")
        return self


class DefenseOutcome(StrictModel):
    """同任务配对后的效果与效用；不能用模型自报完成填充。"""

    schema_version: Literal["18.0"] = "18.0"
    outcome_id: NonEmptyStr
    before_run_id: NonEmptyStr
    after_run_id: NonEmptyStr
    before_effect_ids: tuple[NonEmptyStr, ...]
    after_effect_ids: tuple[NonEmptyStr, ...]
    before_authorization: tuple[bool, ...]
    after_authorization: tuple[bool, ...]
    task_success: bool
    safe_task_success: bool
    utility_loss: Annotated[int, Field(ge=-1, le=1)]
    over_defense: bool
    residual_risk: bool
    actual_extra_steps: Annotated[int, Field(ge=0)]
    actual_latency_ms: Annotated[float, Field(ge=0)]
    evidence_ids: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_effect_alignment(self) -> Self:
        """每个效果保存自己的授权真值，任务成功不能替代安全成功。"""
        if len(self.before_effect_ids) != len(self.before_authorization) or len(
            self.after_effect_ids
        ) != len(self.after_authorization):
            raise ValueError("t18_outcome_authorization_alignment")
        if self.safe_task_success != (self.task_success and not self.residual_risk):
            raise ValueError("t18_safe_task_conjunction")
        return self
