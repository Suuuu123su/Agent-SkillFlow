"""断言检查器与证据序列化之间的内部类型边界。"""

from dataclasses import dataclass

from skillflow.experiment.t16.task_success_evidence import (
    AssertionStatus,
    EvidenceReason,
    EvidenceSource,
)


@dataclass(frozen=True, slots=True)
class AssertionObservation:
    """一条断言的最小平台观察，不携带正文。"""

    status: AssertionStatus
    source: EvidenceSource
    reason: EvidenceReason
    session_id: str | None = None
    artifact_id: str | None = None
    artifact_alias: str | None = None
    artifact_content_sha256: str | None = None
    effect_id: str | None = None
    receipt_id: str | None = None
    safe_sink_commitment_sha256: str | None = None
    expected_value_commitment_sha256: str | None = None
    observed_value_commitment_sha256: str | None = None
