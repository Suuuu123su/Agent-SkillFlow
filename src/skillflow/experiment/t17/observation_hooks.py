"""T17 六类 Hook 的证据可用性计算。"""

from dataclasses import dataclass
from typing import assert_never

from skillflow.experiment.t17.contracts import (
    HookCapability,
    HookName,
    MeasurementStatus,
)
from skillflow.experiment.t17.observation_models import (
    AuthorizationObservation,
    DecisionBasisObservation,
    InfluenceObservation,
    ProvenanceObservation,
    RevocationObservation,
)
from skillflow.experiment.t17.task_evidence import T17TaskSuccessEvidence


@dataclass(frozen=True, slots=True)
class HookEvidenceBundle:
    """六类 Hook 已由运行事实生成的证据集合。"""

    authorizations: tuple[AuthorizationObservation, ...]
    decisions: tuple[DecisionBasisObservation, ...]
    provenance: tuple[ProvenanceObservation, ...]
    revocations: tuple[RevocationObservation, ...]
    influences: tuple[InfluenceObservation, ...]
    task: T17TaskSuccessEvidence | None


def hook_capabilities(
    required_hooks: frozenset[HookName],
    evidence: HookEvidenceBundle,
) -> tuple[HookCapability, ...]:
    """只把有受信证据的 required Hook 标为 measured。"""
    values = []
    for hook in HookName:
        required = hook in required_hooks
        evidence_ids = _hook_evidence_ids(hook, evidence)
        available = bool(evidence_ids)
        status = MeasurementStatus.MEASURED if available else MeasurementStatus.NOT_AVAILABLE
        reason = None if available else "required Hook 没有受信运行证据"
        if not required:
            available = False
            status = MeasurementStatus.NOT_APPLICABLE
            reason = "该 Run 的场景设计不要求此 Hook"
            evidence_ids = ()
        values.append(
            HookCapability(
                hook=hook,
                required=required,
                available=available,
                status=status,
                reason=reason,
                evidence_ids=evidence_ids,
            )
        )
    return tuple(values)


def _hook_evidence_ids(
    hook: HookName,
    evidence: HookEvidenceBundle,
) -> tuple[str, ...]:
    match hook:
        case HookName.AUTHORIZATION:
            return tuple(
                dict.fromkeys(
                    (
                        *(item.grant_event_id for item in evidence.authorizations),
                        *(item.decision_id for item in evidence.decisions),
                    )
                )
            )
        case HookName.DECISION_BASIS:
            return tuple(
                item.decision_id for item in evidence.decisions if item.decision_basis_artifact_ids
            )
        case HookName.PROVENANCE:
            return tuple(item.artifact_id for item in evidence.provenance)
        case HookName.INFLUENCE:
            return tuple(item.replay_id for item in evidence.influences)
        case HookName.REVOCATION:
            return tuple(item.event_id for item in evidence.revocations)
        case HookName.TASK_SUCCESS:
            return () if evidence.task is None else evidence.task.evidence_ids
        case unreachable:
            assert_never(unreachable)
