"""授权匹配、来源证据与决策组合值对象。"""

from dataclasses import dataclass
from datetime import datetime

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Decision, EnforcementMode, TrustLevel
from skillflow.models.manifest import SkillManifest
from skillflow.policy.reasons import PolicyReasonCode


@dataclass(frozen=True, slots=True)
class AuthorizationBoundary:
    """一个 Effect 判断时的 Task、Session、Call 与时间边界。"""

    task_id: str
    session_id: str
    call_id: str
    effect_time: datetime


@dataclass(frozen=True, slots=True)
class ManifestMatch:
    """Manifest capability matcher 的可追踪结果。"""

    matched: bool
    manifest_id: str
    permission_indexes: tuple[int, ...]
    reason_codes: tuple[PolicyReasonCode, ...]


@dataclass(frozen=True, slots=True)
class GrantMatchRequest:
    """Grant matcher 所需的完整运行边界。"""

    actor_id: str
    effect: CapabilityEffect
    boundary: AuthorizationBoundary
    revoked_grant_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class GrantMatch:
    """全部相关 Grant 的聚合匹配结果。"""

    matched_grant_ids: tuple[str, ...]
    reason_codes: tuple[PolicyReasonCode, ...]


@dataclass(frozen=True, slots=True)
class ProvenanceEvidence:
    """PolicyEngine 可读取的 Observed 来源摘要。"""

    artifact_ids: tuple[str, ...] = ()
    origins: frozenset[str] = frozenset()
    trust_levels: frozenset[TrustLevel] = frozenset()
    revoked_origins: frozenset[str] = frozenset()
    complete: bool = True


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    """Manifest、Grant、边界与来源组成的策略请求。"""

    manifest: SkillManifest
    grants: tuple[AuthorizationGrant, ...]
    grant_request: GrantMatchRequest
    provenance: ProvenanceEvidence = ProvenanceEvidence()
    confirmation_allowed: bool = True


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    """不包含 Harness baseline 的纯策略结果。"""

    policy_result: Decision
    authorized: bool
    manifest_id: str
    manifest_matched: bool
    valid_grant_matched: bool
    matched_grant_ids: tuple[str, ...]
    decision_basis_artifact_ids: tuple[str, ...]
    reason_codes: tuple[PolicyReasonCode, ...]


@dataclass(frozen=True, slots=True)
class BaselineFacts:
    """第 5.6 节基线优先级的机械输入。"""

    structurally_valid: bool = True
    structured_confirmation: bool = False
    auto_approve_tools: bool = False
    implicit_text_authorization: bool = False
    text_claim_artifact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BaselineEvaluation:
    """基线决定及真正影响它的文本 Artifact。"""

    result: Decision
    decision_basis_artifact_ids: tuple[str, ...] = ()


class DecisionInputs(StrictModel):
    """组合 baseline、policy 与执行模式的已解析输入。"""

    enforcement_mode: EnforcementMode
    baseline_result: Decision
    policy_result: Decision
    authorized: bool
    manifest_id: NonEmptyStr | None
    decision_basis_artifact_ids: tuple[NonEmptyStr, ...] = ()
    matched_grant_ids: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[PolicyReasonCode, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionPlan:
    """InstrumentedTool 可直接执行的完整决策计划。"""

    enforcement_mode: EnforcementMode
    baseline_result: Decision
    policy_result: Decision
    authorized: bool
    executed: bool
    manifest_id: str | None
    decision_basis_artifact_ids: tuple[str, ...]
    matched_grant_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
