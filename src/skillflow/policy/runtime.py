"""从 EventStore 事实构造纯 PolicyEngine 输入的运行适配器。"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import assert_never

from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Decision, EnforcementMode
from skillflow.models.manifest import SkillManifest
from skillflow.models.provenance import Artifact
from skillflow.policy.baseline import combine_decisions, evaluate_baseline
from skillflow.policy.engine import PolicyEngine
from skillflow.policy.errors import PolicyConfigurationError
from skillflow.policy.models import (
    AuthorizationBoundary,
    BaselineFacts,
    DecisionInputs,
    DecisionPlan,
    GrantMatchRequest,
    PolicyRequest,
    ProvenanceEvidence,
)
from skillflow.store.event_store import EventStore, RevocationRecord, RevocationTargetKind


@dataclass(frozen=True, slots=True)
class RuntimePolicySetup:
    """一个 Run 的 Manifest、基线开关和执行模式。"""

    run_id: str
    manifests: Mapping[str, SkillManifest]
    structural_decisions: Mapping[str, Decision]
    enforcement_mode: EnforcementMode
    auto_approve_tools: bool
    implicit_text_authorization: bool
    confirmation_allowed: bool = True


@dataclass(frozen=True, slots=True)
class PolicyToolRequest:
    """一次 Tool 请求交给策略适配器的中立事实。"""

    decision_key: str
    actor_id: str
    argument_artifact_id: str
    effect: CapabilityEffect
    boundary: AuthorizationBoundary
    source_artifacts: tuple[Artifact, ...] = ()
    text_claim_artifact_ids: tuple[str, ...] = ()


class StoredPolicyDecisionProvider:
    """只读取 Observed EventStore，不读取 Oracle 的正式决策器。"""

    def __init__(self, store: EventStore, setup: RuntimePolicySetup) -> None:
        """复制调用方映射，冻结当前 Run 的策略配置。"""
        self._store = store
        self._run_id = setup.run_id
        self._manifests = dict(setup.manifests)
        self._structural_decisions = dict(setup.structural_decisions)
        self._enforcement_mode = setup.enforcement_mode
        self._auto_approve_tools = setup.auto_approve_tools
        self._implicit_text_authorization = setup.implicit_text_authorization
        self._confirmation_allowed = setup.confirmation_allowed
        self._engine = PolicyEngine()

    def evaluate(self, request: PolicyToolRequest) -> DecisionPlan:
        """从当前追加事实计算 baseline、policy、authorized 和 executed。"""
        manifest = self._manifest(request.actor_id)
        revocations = tuple(
            item
            for item in self._store.iter_run_revocations(self._run_id)
            if item.timestamp <= request.boundary.effect_time
        )
        provenance = _provenance_evidence(request.source_artifacts, revocations)
        policy = self._engine.evaluate(
            PolicyRequest(
                manifest=manifest,
                grants=self._store.iter_run_grants(self._run_id),
                grant_request=GrantMatchRequest(
                    actor_id=request.actor_id,
                    effect=request.effect,
                    boundary=request.boundary,
                    revoked_grant_ids=frozenset(
                        item.target_id
                        for item in revocations
                        if item.target_kind is RevocationTargetKind.GRANT
                    ),
                ),
                provenance=provenance,
                confirmation_allowed=self._confirmation_allowed,
            )
        )
        baseline = evaluate_baseline(
            BaselineFacts(
                structurally_valid=self._structurally_valid(request.decision_key),
                structured_confirmation=policy.valid_grant_matched,
                auto_approve_tools=self._auto_approve_tools,
                implicit_text_authorization=self._implicit_text_authorization,
                text_claim_artifact_ids=request.text_claim_artifact_ids,
            )
        )
        plan = combine_decisions(
            DecisionInputs(
                enforcement_mode=self._enforcement_mode,
                baseline_result=baseline.result,
                policy_result=policy.policy_result,
                authorized=policy.authorized,
                manifest_id=policy.manifest_id,
                decision_basis_artifact_ids=policy.decision_basis_artifact_ids,
                matched_grant_ids=policy.matched_grant_ids,
                reason_codes=policy.reason_codes,
            )
        )
        basis = tuple(
            dict.fromkeys(
                (
                    request.argument_artifact_id,
                    *plan.decision_basis_artifact_ids,
                    *baseline.decision_basis_artifact_ids,
                )
            )
        )
        return replace(plan, decision_basis_artifact_ids=basis)

    def _manifest(self, actor_id: str) -> SkillManifest:
        try:
            return self._manifests[actor_id]
        except KeyError as error:
            raise PolicyConfigurationError(actor_id, "Skill 缺少 Manifest") from error

    def _structurally_valid(self, decision_key: str) -> bool:
        try:
            decision = self._structural_decisions[decision_key]
        except KeyError as error:
            raise PolicyConfigurationError(decision_key, "缺少结构基线 fixture") from error
        match decision:
            case Decision.ALLOW | Decision.CONFIRM:
                return True
            case Decision.DENY:
                return False
            case _ as unreachable:
                assert_never(unreachable)


def _provenance_evidence(
    artifacts: tuple[Artifact, ...],
    revocations: tuple[RevocationRecord, ...],
) -> ProvenanceEvidence:
    origins = frozenset(
        origin for artifact in artifacts for origin in artifact.observed_label.origins
    )
    revoked_principals = frozenset(
        item.target_id for item in revocations if item.target_kind is RevocationTargetKind.PRINCIPAL
    )
    inherited_revoked = frozenset(
        origin for artifact in artifacts for origin in artifact.observed_label.revoked_origins
    )
    return ProvenanceEvidence(
        artifact_ids=tuple(artifact.artifact_id for artifact in artifacts),
        origins=origins,
        trust_levels=frozenset(artifact.observed_label.trust for artifact in artifacts),
        revoked_origins=inherited_revoked | (origins & revoked_principals),
        complete=all(bool(artifact.observed_label.origins) for artifact in artifacts),
    )
