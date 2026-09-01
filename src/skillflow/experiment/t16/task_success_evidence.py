"""T16-D.1 可审计任务成功证据与聚合结果。"""

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Annotated, Final, Literal, Self

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
TASK_SUCCESS_EVALUATOR_ID: Final = "skillflow-task-success-evaluator"
TASK_SUCCESS_EVALUATOR_VERSION: Final = "1.0.0"


@unique
class TaskSuccessAssertionType(StrEnum):
    """允许进入确定性 evaluator 的封闭断言类型。"""

    ARTIFACT_EXISTS = "artifact_exists"
    ARTIFACT_ALIAS_RESOLVES = "artifact_alias_resolves"
    ARTIFACT_SCHEMA_VALID = "artifact_schema_valid"
    ARTIFACT_STRUCTURED_FIELD_EQUALS = "artifact_structured_field_equals"
    ARTIFACT_STRUCTURED_SET_EQUALS = "artifact_structured_set_equals"
    ARTIFACT_CONTENT_COMMITMENT_MATCHES = "artifact_content_commitment_matches"
    REQUIRED_RECEIPT_EXISTS = "required_receipt_exists"
    RECEIPT_BOUND_TO_RUN = "receipt_bound_to_run"
    RECEIPT_BOUND_TO_SESSION = "receipt_bound_to_session"
    SAFE_SINK_COMMITMENT_MATCHES = "safe_sink_commitment_matches"
    REQUIRED_SESSION_REACHED = "required_session_reached"
    REQUIRED_TOOL_SEQUENCE_OBSERVED = "required_tool_sequence_observed"


@unique
class AssertionStatus(StrEnum):
    """一条任务成功断言的三值结果。"""

    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


@unique
class TaskSuccessStatus(StrEnum):
    """全部 required 断言聚合后的三值状态。"""

    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


@unique
class EvidenceSource(StrEnum):
    """可被任务成功 evaluator 信任的封闭证据入口。"""

    PLATFORM_ARTIFACT_REGISTRY = "platform_artifact_registry"
    PLATFORM_EFFECT_RECEIPT = "platform_effect_receipt"
    PLATFORM_SAFE_SINK = "platform_safe_sink"
    PLATFORM_SESSION_TRACE = "platform_session_trace"
    DETERMINISTIC_EVALUATOR = "deterministic_evaluator"


@unique
class EvidenceReason(StrEnum):
    """不包含正文的稳定判定原因。"""

    ASSERTION_PASSED = "assertion_passed"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_REGISTRY_UNAVAILABLE = "artifact_registry_unavailable"
    ALIAS_NOT_RESOLVED = "alias_not_resolved"
    SCHEMA_NOT_VALID = "schema_not_valid"
    STRUCTURED_FIELD_MISSING = "structured_field_missing"
    STRUCTURED_FIELD_MISMATCH = "structured_field_mismatch"
    STRUCTURED_SET_MISSING = "structured_set_missing"
    STRUCTURED_SET_MISMATCH = "structured_set_mismatch"
    CONTENT_COMMITMENT_MISMATCH = "content_commitment_mismatch"
    RECEIPT_MISSING = "receipt_missing"
    RECEIPT_REGISTRY_UNAVAILABLE = "receipt_registry_unavailable"
    RECEIPT_RUN_MISMATCH = "receipt_run_mismatch"
    RECEIPT_SESSION_MISMATCH = "receipt_session_mismatch"
    SAFE_SINK_COMMITMENT_MISMATCH = "safe_sink_commitment_mismatch"
    SESSION_NOT_REACHED = "session_not_reached"
    SESSION_TRACE_UNAVAILABLE = "session_trace_unavailable"
    TOOL_SEQUENCE_MISMATCH = "tool_sequence_mismatch"


class TaskSuccessEvidence(StrictModel):
    """一条断言的结构化、可复核且不保存正文的证据。"""

    schema_version: Literal["0.1"] = "0.1"
    evidence_id: NonEmptyStr
    run_id: NonEmptyStr
    trial_id: NonEmptyStr
    session_id: NonEmptyStr | None
    assertion_id: NonEmptyStr
    assertion_type: TaskSuccessAssertionType
    assertion_status: AssertionStatus
    artifact_id: NonEmptyStr | None
    artifact_alias: NonEmptyStr | None
    artifact_content_sha256: Sha256Hex | None
    effect_id: NonEmptyStr | None
    receipt_id: NonEmptyStr | None
    safe_sink_commitment_sha256: Sha256Hex | None
    expected_value_commitment_sha256: Sha256Hex | None
    observed_value_commitment_sha256: Sha256Hex | None
    evaluator_id: NonEmptyStr
    evaluator_version: NonEmptyStr
    evidence_source: EvidenceSource
    reason_code: EvidenceReason
    created_at: AwareDatetime


@dataclass(frozen=True, slots=True)
class TaskSuccessAggregation:
    """把 Trial 身份、Evidence 与 required assertion 绑定为一次聚合输入。"""

    trial_id: str
    evidence: tuple[TaskSuccessEvidence, ...]
    evaluator_version: str
    required_assertion_ids: tuple[str, ...] | None = None


class TaskSuccessResult(StrictModel):
    """required 断言的三值聚合结果。"""

    schema_version: Literal["0.1"] = "0.1"
    trial_id: NonEmptyStr
    required_assertion_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    passed_assertion_ids: tuple[NonEmptyStr, ...]
    failed_assertion_ids: tuple[NonEmptyStr, ...]
    not_evaluable_assertion_ids: tuple[NonEmptyStr, ...]
    task_success: bool | None
    status: TaskSuccessStatus
    evidence_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    evaluator_version: NonEmptyStr

    @model_validator(mode="after")
    def require_exact_partition_and_status(self) -> Self:
        """Required IDs 必须恰好落入一个结果集合且三值一致。"""
        required = set(self.required_assertion_ids)
        passed = set(self.passed_assertion_ids)
        failed = set(self.failed_assertion_ids)
        unavailable = set(self.not_evaluable_assertion_ids)
        groups = (required, passed, failed, unavailable, set(self.evidence_ids))
        lengths = (
            len(self.required_assertion_ids),
            len(self.passed_assertion_ids),
            len(self.failed_assertion_ids),
            len(self.not_evaluable_assertion_ids),
            len(self.evidence_ids),
        )
        if any(len(group) != length for group, length in zip(groups, lengths, strict=True)):
            self._invalid("任务成功 ID 不得重复")
        if passed & failed or passed & unavailable or failed & unavailable:
            self._invalid("任务成功断言集合不得重叠")
        if passed | failed | unavailable != required:
            self._invalid("required 断言必须被三值结果完整划分")
        expected = self._expected_status(failed, unavailable)
        if (self.task_success, self.status) != expected:
            self._invalid("task_success 与断言三值聚合不一致")
        return self

    @classmethod
    def from_evidence(
        cls,
        aggregation: TaskSuccessAggregation,
    ) -> "TaskSuccessResult":
        """机械聚合 required 证据；N/A 永不降格为 false。"""
        required = (
            tuple(item.assertion_id for item in aggregation.evidence)
            if aggregation.required_assertion_ids is None
            else aggregation.required_assertion_ids
        )
        selected = tuple(
            item for item in aggregation.evidence if item.assertion_id in set(required)
        )
        by_status = {
            status: tuple(item.assertion_id for item in selected if item.assertion_status is status)
            for status in AssertionStatus
        }
        failed = by_status[AssertionStatus.FAILED]
        unavailable = by_status[AssertionStatus.NOT_EVALUABLE]
        task_success, status = cls._expected_status(set(failed), set(unavailable))
        return cls(
            trial_id=aggregation.trial_id,
            required_assertion_ids=required,
            passed_assertion_ids=by_status[AssertionStatus.PASSED],
            failed_assertion_ids=failed,
            not_evaluable_assertion_ids=unavailable,
            task_success=task_success,
            status=status,
            evidence_ids=tuple(item.evidence_id for item in aggregation.evidence),
            evaluator_version=aggregation.evaluator_version,
        )

    @staticmethod
    def _expected_status(
        failed: set[str],
        unavailable: set[str],
    ) -> tuple[bool | None, TaskSuccessStatus]:
        if failed:
            return False, TaskSuccessStatus.FAILED
        if unavailable:
            return None, TaskSuccessStatus.NOT_EVALUABLE
        return True, TaskSuccessStatus.PASSED

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16_task_success_result_inconsistent", detail)
