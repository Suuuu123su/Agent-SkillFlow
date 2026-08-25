"""仅供 Benchmark 编排器持有的可信控制面。"""

from typing import Protocol

from skillflow.instrumentation.artifact_intervention import (
    ArtifactInterventionMode,
    ArtifactInterventionResult,
)
from skillflow.instrumentation.errors import HarnessStateError
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.enums import PrincipalType
from skillflow.models.provenance import Artifact
from skillflow.runtime.session import ActorCall


class _BenchmarkHarness(Protocol):
    def benchmark_revoke_skill(self, skill_id: str, actor: ActorCall) -> None: ...

    def benchmark_unload_skill(self, skill_id: str, actor: ActorCall) -> None: ...

    def benchmark_issue_grant(self, grant: AuthorizationGrant, actor: ActorCall) -> None: ...

    def benchmark_revoke_grant(self, grant_id: str, actor: ActorCall) -> None: ...

    def benchmark_add_context(self, content: bytes, actor: ActorCall) -> Artifact: ...

    def benchmark_write_memory(
        self,
        key: str,
        source_artifact_id: str,
        actor: ActorCall,
    ) -> Artifact: ...

    def benchmark_intervene_artifact(
        self,
        source_artifact_id: str,
        mode: ArtifactInterventionMode,
    ) -> ArtifactInterventionResult: ...


class BenchmarkController:
    """不暴露给 Skill 的用户确认、状态准备与撤销接口。"""

    def __init__(self, harness: _BenchmarkHarness) -> None:
        """绑定唯一 Harness，不向 ScriptedBackend 暴露该控制器。"""
        self._harness = harness

    def revoke_skill(self, skill_id: str, actor: PrincipalType) -> None:
        """仅允许 Benchmark 以可信主体撤销 Skill。"""
        self._require_trusted(actor, "revoke_skill")
        self._harness.benchmark_revoke_skill(skill_id, ActorCall(actor.value, None))

    def unload_skill(self, skill_id: str, actor: PrincipalType) -> None:
        """仅允许 Benchmark 以可信主体卸载 Skill。"""
        self._require_trusted(actor, "unload_skill")
        self._harness.benchmark_unload_skill(skill_id, ActorCall(actor.value, None))

    def confirm_tool(self, grant: AuthorizationGrant, actor: PrincipalType) -> None:
        """由 USER/TRUSTED_POLICY 特权确认生成结构化 Grant。"""
        self._require_trusted(actor, "confirm_tool")
        if grant.issuer_type is not actor:
            raise HarnessStateError("confirm_tool", "actor and issuer_type mismatch")
        self._harness.benchmark_issue_grant(grant, ActorCall(grant.issuer_id, None))

    def revoke_grant(self, grant_id: str, actor: PrincipalType) -> None:
        """由可信 Benchmark 主体撤销 Grant。"""
        self._require_trusted(actor, "revoke_grant")
        self._harness.benchmark_revoke_grant(grant_id, ActorCall(actor.value, None))

    def add_context(self, content: bytes, actor: PrincipalType) -> Artifact:
        """由可信 Benchmark 主体建立 Context 测试前缀。"""
        self._require_trusted(actor, "add_context")
        return self._harness.benchmark_add_context(content, ActorCall(actor.value, None))

    def write_memory(
        self,
        key: str,
        source_artifact_id: str,
        actor: PrincipalType,
    ) -> Artifact:
        """由可信 Benchmark 主体建立 Persistent Memory 测试前缀。"""
        self._require_trusted(actor, "write_memory")
        return self._harness.benchmark_write_memory(
            key,
            source_artifact_id,
            ActorCall(actor.value, None),
        )

    def intervene_artifact(
        self,
        source_artifact_id: str,
        mode: ArtifactInterventionMode,
    ) -> ArtifactInterventionResult:
        """执行 T10 固定 identity/neutral Artifact 派生。"""
        return self._harness.benchmark_intervene_artifact(source_artifact_id, mode)

    @staticmethod
    def _require_trusted(actor: PrincipalType, operation: str) -> None:
        if actor not in {PrincipalType.USER, PrincipalType.TRUSTED_POLICY}:
            raise HarnessStateError(operation, f"untrusted actor: {actor.value}")
