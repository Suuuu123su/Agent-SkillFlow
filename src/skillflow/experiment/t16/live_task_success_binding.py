"""LiveTrialRecord v0.3 与 TaskSuccessEvidence 的严格绑定。"""

from dataclasses import dataclass
from typing import NoReturn, Protocol

from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.task_success_evidence import (
    TASK_SUCCESS_EVALUATOR_ID,
    TASK_SUCCESS_EVALUATOR_VERSION,
    TaskSuccessAggregation,
    TaskSuccessEvidence,
    TaskSuccessResult,
)
from skillflow.experiment.t16.trial import TrialResult


class LiveTaskSuccessRecordView(Protocol):
    """v0.3 绑定器实际读取的最小只读 Record 视图。"""

    @property
    def run_id(self) -> str | None:
        """返回 Record 的平台 Run ID。"""
        ...

    @property
    def result(self) -> TrialResult:
        """返回统一 Trial 结果。"""
        ...

    @property
    def task_success_evidence(self) -> tuple[TaskSuccessEvidence, ...]:
        """返回有序 TaskSuccessEvidence。"""
        ...

    @property
    def task_success_result(self) -> TaskSuccessResult | None:
        """返回三值聚合结果。"""
        ...


@dataclass(frozen=True, slots=True)
class ParsedTaskSuccessBinding:
    """已确认必填字段存在的 v0.3 绑定。"""

    run_id: str
    evidence: tuple[TaskSuccessEvidence, ...]
    result: TaskSuccessResult


def require_live_task_success_binding(record: LiveTaskSuccessRecordView) -> None:
    """重算 Evidence 分区并绑定固定 evaluator、Run 与 Trial。"""
    binding = _parse_binding(record)
    _require_identity(record.result.trial_id, binding)
    _require_evaluator(binding)
    _require_aggregation(record.result, binding)


def _parse_binding(record: LiveTaskSuccessRecordView) -> ParsedTaskSuccessBinding:
    if record.run_id is None or not record.task_success_evidence:
        _invalid("0.3 Live Trial 缺少 Run 或 TaskSuccessEvidence")
    if record.task_success_result is None:
        _invalid("0.3 Live Trial 缺少 TaskSuccessResult")
    return ParsedTaskSuccessBinding(
        run_id=record.run_id,
        evidence=record.task_success_evidence,
        result=record.task_success_result,
    )


def _require_identity(trial_id: str, binding: ParsedTaskSuccessBinding) -> None:
    if binding.result.trial_id != trial_id:
        _invalid("TaskSuccessResult 与 Trial ID 不一致")
    if any(item.trial_id != trial_id for item in binding.evidence):
        _invalid("TaskSuccessEvidence 与 Trial ID 不一致")
    if any(item.run_id != binding.run_id for item in binding.evidence):
        _invalid("TaskSuccessEvidence 与 Run ID 不一致")
    evidence_ids = tuple(item.evidence_id for item in binding.evidence)
    if binding.result.evidence_ids != evidence_ids:
        _invalid("TaskSuccessResult 与 Evidence ID 不一致")


def _require_evaluator(binding: ParsedTaskSuccessBinding) -> None:
    if any(item.evaluator_id != TASK_SUCCESS_EVALUATOR_ID for item in binding.evidence):
        _invalid("TaskSuccess evaluator ID 未注册")
    versions = (
        binding.result.evaluator_version,
        *(item.evaluator_version for item in binding.evidence),
    )
    if any(item != TASK_SUCCESS_EVALUATOR_VERSION for item in versions):
        _invalid("TaskSuccess evaluator 版本未注册")


def _require_aggregation(trial: TrialResult, binding: ParsedTaskSuccessBinding) -> None:
    recomputed = TaskSuccessResult.from_evidence(
        TaskSuccessAggregation(
            trial_id=trial.trial_id,
            evidence=binding.evidence,
            evaluator_version=binding.result.evaluator_version,
            required_assertion_ids=binding.result.required_assertion_ids,
        )
    )
    if recomputed != binding.result:
        _invalid("TaskSuccess Evidence 与聚合结果不一致")
    if trial.task_success is not binding.result.task_success:
        _invalid("TrialResult 与 TaskSuccessResult 三值不一致")


def _invalid(detail: str) -> NoReturn:
    raise PydanticCustomError("t16c_live_record_inconsistent", detail)
