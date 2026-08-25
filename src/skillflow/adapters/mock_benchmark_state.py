"""Mock Harness 的 Benchmark-only 状态操作。"""

from abc import ABC, abstractmethod

from skillflow.adapters.mock_session import MockSessionRuntime
from skillflow.instrumentation.artifact_intervention import (
    ArtifactInterventionMode,
    ArtifactInterventionResult,
    intervene_artifact,
)
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.provenance import Artifact
from skillflow.runtime.session import ActorCall


class MockBenchmarkStateMixin(ABC):
    """把 Skill 不可见的状态准备与撤销操作集中在独立控制面。"""

    @abstractmethod
    def _require_runtime(self, operation: str) -> MockSessionRuntime:
        """由具体 Harness 提供活动 Session。"""

    def benchmark_revoke_skill(self, skill_id: str, actor: ActorCall) -> None:
        """仅供 BenchmarkController 调用的撤销入口。"""
        self._require_runtime("revoke_skill").skills.revoke(skill_id, actor)

    def benchmark_add_context(self, content: bytes, actor: ActorCall) -> Artifact:
        """仅供 BenchmarkController 建立受控 Context 前缀。"""
        return self._require_runtime("add_context").context.add(content, actor)

    def benchmark_write_memory(
        self,
        key: str,
        source_artifact_id: str,
        actor: ActorCall,
    ) -> Artifact:
        """仅供 BenchmarkController 建立受控 Memory 前缀。"""
        return self._require_runtime("write_memory").memory.write(
            key,
            source_artifact_id,
            actor,
        )

    def benchmark_intervene_artifact(
        self,
        source_artifact_id: str,
        mode: ArtifactInterventionMode,
    ) -> ArtifactInterventionResult:
        """仅供 BenchmarkController 追加结构保持的派生版本。"""
        runtime = self._require_runtime("intervene_artifact")
        return intervene_artifact(runtime.recorder, source_artifact_id, mode)

    def benchmark_unload_skill(self, skill_id: str, actor: ActorCall) -> None:
        """仅供 BenchmarkController 调用的卸载入口。"""
        self._require_runtime("unload_skill").skills.unload(skill_id, actor)

    def benchmark_issue_grant(self, grant: AuthorizationGrant, actor: ActorCall) -> None:
        """仅供 BenchmarkController 调用的结构化确认入口。"""
        self._require_runtime("confirm_tool").recorder.record_authorization_grant(grant, actor)

    def benchmark_revoke_grant(self, grant_id: str, actor: ActorCall) -> None:
        """仅供 BenchmarkController 调用的 Grant 撤销入口。"""
        self._require_runtime("revoke_grant").recorder.record_authorization_revocation(
            grant_id,
            actor,
        )
