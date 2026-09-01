"""T16-C 真实模型、纯本地 Effect 的可审计记录。"""

from decimal import Decimal
from typing import Annotated, Literal, NoReturn, Self

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.dry_run_records import SessionEffectObservation
from skillflow.experiment.t16.live_record_schema import LIVE_TRIAL_SCHEMA_EXTRA
from skillflow.experiment.t16.live_session_models import LiveSessionRecord, LiveToolCallAudit
from skillflow.experiment.t16.live_task_success_binding import (
    require_live_task_success_binding,
)
from skillflow.experiment.t16.preregistration_models import (
    IndependentFactor,
    PairRole,
    T16Intervention,
)
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_evidence import (
    TaskSuccessEvidence,
    TaskSuccessResult,
)
from skillflow.experiment.t16.trial import TrialResult
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.references import EffectSelectorRef

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

__all__ = ("LiveSessionRecord", "LiveToolCallAudit", "LiveTrialRecord")


class LiveTrialRecord(StrictModel):
    """真实模型判断与模拟 Effect 明确分层的完整 Trial 证据。"""

    model_config = ConfigDict(json_schema_extra=LIVE_TRIAL_SCHEMA_EXTRA)

    schema_version: Literal["0.1", "0.2", "0.3"]
    simulation_only: Literal[False] = False
    live_model: Literal[True] = True
    external_effects_simulated: Literal[True] = True
    run_id: NonEmptyStr | None = None
    matrix_trial_id: NonEmptyStr
    pair_role: PairRole
    independent_factor: IndependentFactor
    hiaa_cell: HiaaCell | None = None
    harm_selector: EffectSelectorRef | None = None
    session_observations: tuple[SessionEffectObservation, ...] = ()
    authorization_request_id: NonEmptyStr | None = None
    structured_target_authorized: bool = False
    unauthorized_effect_execution: bool
    decision_basis_artifact_ids: tuple[NonEmptyStr, ...] = ()
    baseline_reason: NonEmptyStr | None = None
    intervention: T16Intervention = T16Intervention.NONE
    intervention_removed_fields: tuple[NonEmptyStr, ...] = ()
    retry_events: tuple[NonEmptyStr, ...] = ()
    model_input_sha256: NonEmptyStr
    phase_contract_sha256: Sha256Hex | None = None
    expected_target_effect_aliases: tuple[NonEmptyStr, ...] = ()
    sessions: tuple[LiveSessionRecord, ...]
    result: TrialResult
    task_success_evidence: tuple[TaskSuccessEvidence, ...] = ()
    task_success_result: TaskSuccessResult | None = None

    @model_validator(mode="after")
    def require_authorization_and_intervention_consistency(self) -> Self:
        """锁定授权、Receipt、ALR 归因和中和审计之间的一致性。"""
        expected_unauthorized = (
            self.result.target_effect_executed and not self.structured_target_authorized
        )
        if self.unauthorized_effect_execution != expected_unauthorized:
            raise PydanticCustomError(
                "t16c_unauthorized_effect_mismatch",
                "未授权执行标记与 Receipt/结构化授权不一致",
            )
        neutralized = self.intervention is T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM
        if neutralized != (self.intervention_removed_fields == ("authorization_claim",)):
            raise PydanticCustomError(
                "t16c_intervention_audit_mismatch",
                "A1 中和必须且只能删除 authorization_claim",
            )
        if self.baseline_reason == "IMPLICIT_TEXT_AUTHORIZATION" and (
            self.authorization_request_id is None or not self.result.target_effect_executed
        ):
            raise PydanticCustomError(
                "t16c_alr_reason_without_receipt",
                "隐式文本授权归因必须绑定授权请求与真实 Receipt",
            )
        if self.schema_version in {"0.2", "0.3"}:
            if self.phase_contract_sha256 is None:
                raise PydanticCustomError(
                    "t16c_phase_contract_missing",
                    "0.2/0.3 Live Trial 必须绑定 phase_contract_sha256",
                )
            self._require_v02_execution_consistency()
        if self.schema_version == "0.3":
            require_live_task_success_binding(self)
        elif (
            self.run_id is not None
            or self.task_success_evidence
            or self.task_success_result is not None
        ):
            self._invalid("旧记录不得回填 TaskSuccessEvidence")
        return self

    def _require_v02_execution_consistency(self) -> None:
        """从 0.2 原始 Session audit 重算目标请求、Receipt 与遥测。"""
        expected = self._require_v02_session_contract()
        self._require_v02_target_receipts(expected)
        self._require_v02_session_observations()
        self._require_v02_telemetry()

    def _require_v02_session_contract(self) -> set[str]:
        """验证 0.2 Session 时序及其实际 selector 声明。"""
        if not self.sessions:
            self._invalid("0.2 Live Trial 至少包含一个 Session")
        session_indices = tuple(session.session_index for session in self.sessions)
        if len(set(session_indices)) != len(session_indices) or session_indices != tuple(
            sorted(session_indices)
        ):
            self._invalid("Session 索引必须唯一且按时序递增")
        if len(set(self.expected_target_effect_aliases)) != len(
            self.expected_target_effect_aliases
        ):
            self._invalid("Trial 预期实际 selector 不得重复")
        expected = set(self.expected_target_effect_aliases)
        for session in self.sessions:
            if not set(session.expected_target_effect_aliases).issubset(expected):
                self._invalid("Session 预期 selector 必须属于 Trial 预期 selector")
            for call in session.tool_calls:
                if (
                    call.accepted
                    and call.receipt_id is not None
                    and call.effect_alias not in session.expected_target_effect_aliases
                ):
                    self._invalid("Receipt 必须匹配其 Session 的预期实际 selector")
        return expected

    def _require_v02_target_receipts(self, expected: set[str]) -> None:
        """从原始 audit 机械重算 Trial 级目标请求与 Receipt。"""
        tool_calls = tuple(call for session in self.sessions for call in session.tool_calls)
        target_calls = tuple(call for call in tool_calls if call.effect_alias in expected)
        receipts = tuple(call.receipt_id for call in target_calls if call.receipt_id is not None)
        if self.result.target_effect_requested != bool(target_calls):
            self._invalid("target_effect_requested 与原始 Tool audit 不一致")
        if self.result.target_effect_executed != bool(receipts):
            self._invalid("target_effect_executed 与原始 Receipt 不一致")
        expected_receipt = receipts[0] if receipts else None
        if self.result.receipt_id != expected_receipt:
            self._invalid("Trial Receipt ID 与首个目标 Receipt 不一致")

    def _require_v02_session_observations(self) -> None:
        by_index = {session.session_index: session for session in self.sessions}
        observation_indices = tuple(item.session_index for item in self.session_observations)
        if len(set(observation_indices)) != len(observation_indices):
            self._invalid("Session observation 索引不得重复")
        for observation in self.session_observations:
            session = by_index.get(observation.session_index)
            if session is None:
                self._invalid("Session observation 必须绑定已执行 Session")
            aliases = set(session.expected_target_effect_aliases)
            calls = tuple(call for call in session.tool_calls if call.effect_alias in aliases)
            receipts = tuple(call.receipt_id for call in calls if call.receipt_id is not None)
            if observation.target_effect_requested != bool(calls):
                self._invalid("Session target request 与本 Session audit 不一致")
            if observation.target_effect_executed != bool(receipts):
                self._invalid("Session target execution 与本 Session Receipt 不一致")
            expected_receipt = receipts[0] if receipts else None
            if observation.receipt_id != expected_receipt:
                self._invalid("Session Receipt ID 不一致")

    def _require_v02_telemetry(self) -> None:
        if self.result.api_call_count != sum(item.api_call_count for item in self.sessions):
            self._invalid("API 调用总数与 Session 不一致")
        if self.result.latency_ms != sum(item.latency_ms for item in self.sessions):
            self._invalid("延迟总数与 Session 不一致")
        cost = sum((item.estimated_cost_usd for item in self.sessions), start=Decimal(0))
        if self.result.estimated_cost_usd != cost:
            self._invalid("费用总数与 Session 不一致")
        usage = TokenUsage(
            input_tokens=sum(item.token_usage.input_tokens for item in self.sessions),
            cached_input_tokens=sum(item.token_usage.cached_input_tokens for item in self.sessions),
            output_tokens=sum(item.token_usage.output_tokens for item in self.sessions),
            reasoning_tokens=sum(item.token_usage.reasoning_tokens for item in self.sessions),
            cache_write_tokens=sum(item.token_usage.cache_write_tokens for item in self.sessions),
        )
        if self.result.token_usage != usage:
            self._invalid("Token 用量与 Session 不一致")
        requested = self.result.target_effect_requested
        expected_no_call = not requested and any(item.no_call for item in self.sessions)
        boolean_totals = (
            (self.result.refusal, any(item.refusal for item in self.sessions)),
            (self.result.no_call, expected_no_call),
            (
                self.result.schema_rejection,
                any(item.schema_rejection for item in self.sessions),
            ),
            (self.result.timeout, any(item.timeout for item in self.sessions)),
            (self.result.rate_limit, any(item.rate_limit for item in self.sessions)),
            (self.result.provider_error, any(item.provider_error for item in self.sessions)),
        )
        if any(actual != expected for actual, expected in boolean_totals):
            self._invalid("Trial 终态布尔值与 Session 不一致")
        if self.schema_version != "0.3" and self.result.task_success != all(
            item.task_success for item in self.sessions
        ):
            self._invalid("Trial task_success 与 Session 不一致")

    @staticmethod
    def _invalid(detail: str) -> NoReturn:
        raise PydanticCustomError("t16c_live_record_inconsistent", detail)
