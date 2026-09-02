"""T17 Reference Harness 的结构化观察模型与绑定请求。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t17.contracts import HookCapability, HookName
from skillflow.experiment.t17.task_evidence import T17TaskSuccessEvidence
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Decision, EnforcementMode, TrustLevel
from skillflow.store.event_store import EventStore, RevocationTargetKind


class AuthorizationObservation(StrictModel):
    """结构化 Grant 及其签发/撤销事实。"""

    grant: AuthorizationGrant
    grant_event_id: NonEmptyStr
    revoked: bool
    revoke_event_id: NonEmptyStr | None = None


class DecisionBasisObservation(StrictModel):
    """一次 Tool 决策真正读取的 Artifact 与授权事实。"""

    decision_id: NonEmptyStr
    request_event_id: NonEmptyStr
    enforcement_mode: EnforcementMode
    baseline_result: Decision
    policy_result: Decision
    authorized: bool
    executed: bool
    decision_basis_artifact_ids: tuple[NonEmptyStr, ...]
    matched_grant_ids: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...]


class ProvenanceObservation(StrictModel):
    """一个 Runtime Artifact 的父边、来源与撤销来源。"""

    artifact_id: NonEmptyStr
    created_by_event_id: NonEmptyStr
    created_session_id: NonEmptyStr
    parent_artifact_ids: frozenset[NonEmptyStr]
    origins: frozenset[NonEmptyStr]
    revoked_origins: frozenset[NonEmptyStr]
    trust: TrustLevel


class EffectObservation(StrictModel):
    """结构化 Tool 请求、决策、执行和同 Run Receipt。"""

    request_event_id: NonEmptyStr
    decision_id: NonEmptyStr
    requested_effect: CapabilityEffect
    accepted: Literal[True] = True
    executed: bool
    effect_id: NonEmptyStr | None = None
    receipt_id: NonEmptyStr | None = None


class RevocationObservation(StrictModel):
    """Grant 或 Principal 撤销的精确 Event 与时点。"""

    revocation_id: NonEmptyStr
    target_kind: RevocationTargetKind
    target_id: NonEmptyStr
    event_id: NonEmptyStr
    timestamp: datetime


class InfluenceObservation(StrictModel):
    """一对 original/neutral 分支的 CI 与确认影响边。"""

    replay_id: NonEmptyStr
    ci: Literal[-1, 0, 1]
    source_artifact_id: NonEmptyStr
    target_effect_ids: tuple[NonEmptyStr, ...]
    evidence_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


class ReferenceObservationSnapshot(StrictModel):
    """一条 Reference Harness Run 的六类 Hook 投影。"""

    schema_version: Literal["0.1"] = "0.1"
    run_id: NonEmptyStr
    hooks: Annotated[tuple[HookCapability, ...], Field(min_length=6, max_length=6)]
    authorizations: tuple[AuthorizationObservation, ...]
    decisions: tuple[DecisionBasisObservation, ...]
    provenance: tuple[ProvenanceObservation, ...]
    effects: tuple[EffectObservation, ...]
    revocations: tuple[RevocationObservation, ...]
    influences: tuple[InfluenceObservation, ...]
    task_success: T17TaskSuccessEvidence | None


@dataclass(frozen=True, slots=True)
class ReferenceObservationRequest:
    """构造受信快照所需的事实源与场景 Hook 要求。"""

    store: EventStore
    run_id: str
    receipts: tuple[ToolReceipt, ...]
    task_success_evidence: T17TaskSuccessEvidence | None
    required_hooks: frozenset[HookName]
    influences: tuple[InfluenceObservation, ...] = ()


class ObservationBindingError(ValueError):
    """Event、Decision、Effect 或 Receipt 绑定不完整。"""

    __slots__ = ("detail", "identifier")

    def __init__(self, identifier: str, detail: str) -> None:
        """保存安全身份与绑定 reason code。"""
        super().__init__(identifier, detail)
        self.identifier = identifier
        self.detail = detail

    def __str__(self) -> str:
        """返回不包含正文的稳定诊断。"""
        return f"{self.identifier}:{self.detail}"
