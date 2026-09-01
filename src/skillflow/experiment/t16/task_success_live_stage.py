"""T16-D.2 Canary 与最终技术门禁。"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from skillflow.experiment.t16.task_success_evaluator import (
    TaskSuccessEvaluation,
    TaskSuccessEvaluationContext,
    evaluate_task_success,
)
from skillflow.experiment.t16.task_success_live_models import (
    T16D2RawTrialRecord,
    T16D2StageGate,
)
from skillflow.experiment.t16.task_success_spec_models import (
    TaskSuccessSpecificationRegistry,
)

SECRET_PATTERNS = (
    re.compile(rb"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(rb"(?i)authorization\s*:\s*bearer"),
    re.compile(rb"(?i)api[_ -]?key"),
)
MAX_INFRASTRUCTURE_RATE = 0.05


@dataclass(frozen=True, slots=True)
class T16D2StageGateInputs:
    """阶段门所需的记录、合同与冻结模型身份。"""

    stage: Literal["canary", "final"]
    records: tuple[T16D2RawTrialRecord, ...]
    registry: TaskSuccessSpecificationRegistry
    expected: int
    raw_path: Path
    expected_model_revision: str


def evaluate_t16d2_stage_gate(
    stage: Literal["canary", "final"],
    records: tuple[T16D2RawTrialRecord, ...],
    registry: TaskSuccessSpecificationRegistry,
    expected: int,
    raw_path: Path,
) -> T16D2StageGate:
    """保留 Model1 调用面，并委托给显式模型身份的通用阶段门。"""
    return evaluate_stage_gate(
        T16D2StageGateInputs(
            stage,
            records,
            registry,
            expected,
            raw_path,
            "gpt-5.6-luna",
        )
    )


def evaluate_stage_gate(inputs: T16D2StageGateInputs) -> T16D2StageGate:  # noqa: C901
    """从已落盘平台快照重算 Evidence，拒绝技术 N/A 与身份漂移。"""
    reasons: list[str] = []
    records = inputs.records
    if len(records) != inputs.expected:
        reasons.append("observed_count_mismatch")
    trial_ids = tuple(item.live_trial.result.trial_id for item in records)
    if len(set(trial_ids)) != len(trial_ids):
        reasons.append("duplicate_trial_id")
    phase_contracts = {
        item.live_trial.phase_contract_sha256
        for item in records
        if item.live_trial.phase_contract_sha256 is not None
    }
    if len(phase_contracts) > 1:
        reasons.append("phase_contract_mismatch")
    specs = {item.spec_id: item for item in inputs.registry.conditions}
    recomputation_valid = True
    for item in records:
        specification = specs.get(item.task_success_spec_id)
        evidence = item.live_trial.task_success_evidence
        stored_result = item.live_trial.task_success_result
        if specification is None or not evidence or stored_result is None:
            recomputation_valid = False
            continue
        recomputed = evaluate_task_success(
            TaskSuccessEvaluationContext(
                run_id=item.live_trial.run_id or "missing-run",
                trial_id=item.live_trial.result.trial_id,
                created_at=evidence[0].created_at,
            ),
            specification.assertions,
            item.platform_evidence_snapshot,
        )
        stored = TaskSuccessEvaluation(
            evidence=evidence,
            result=stored_result,
        )
        if recomputed != stored:
            recomputation_valid = False
    if not recomputation_valid:
        reasons.append("evidence_recomputation_mismatch")
    not_evaluable = sum(
        len(item.live_trial.task_success_result.not_evaluable_assertion_ids)
        for item in records
        if item.live_trial.task_success_result is not None
    )
    if not_evaluable:
        reasons.append("technical_not_evaluable")
    infrastructure = sum(_infrastructure_invalid(item) for item in records)
    if records and infrastructure / len(records) > MAX_INFRASTRUCTURE_RATE:
        reasons.append("infrastructure_invalid_above_5_percent")
    revisions = tuple(
        sorted({revision for item in records for revision in item.provider_model_revisions})
    )
    if (
        any(revision != inputs.expected_model_revision for revision in revisions)
        or len(revisions) > 1
    ):
        reasons.append("provider_model_revision_changed")
    secret_scan = scan_t16d2_secrets(inputs.raw_path)
    if not secret_scan:
        reasons.append("secret_pattern_detected")
    evidence_count = sum(len(item.live_trial.task_success_evidence) for item in records)
    return T16D2StageGate(
        stage=inputs.stage,
        created_at=datetime.now(UTC),
        expected=inputs.expected,
        observed=len(records),
        passed=not reasons,
        reasons=tuple(reasons),
        evidence_count=evidence_count,
        not_evaluable_assertion_count=not_evaluable,
        infrastructure_invalid_count=infrastructure,
        provider_model_revisions=revisions,
        artifact_binding_valid=recomputation_valid,
        receipt_binding_valid=recomputation_valid,
        session_binding_valid=recomputation_valid,
        secret_scan_passed=secret_scan,
    )


def scan_t16d2_secrets(path: Path) -> bool:
    """扫描常见凭据形态；扫描器从不需要知道真实凭据。"""
    content = path.read_bytes()
    return not any(pattern.search(content) for pattern in SECRET_PATTERNS)


def _infrastructure_invalid(record: T16D2RawTrialRecord) -> bool:
    result = record.live_trial.result
    return result.timeout or result.rate_limit or result.provider_error
