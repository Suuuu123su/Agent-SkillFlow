"""Context 转换插桩。"""

from skillflow.instrumentation.errors import ArtifactContentError
from skillflow.models.enums import ArtifactType, EventType, TrustLevel
from skillflow.models.provenance import Artifact
from skillflow.runtime.session import ActorCall, ArtifactEmission, RuntimeRecorder


class InstrumentedContext:
    """每次转换都产生新 Artifact 和 Event 的 Context。"""

    def __init__(self, recorder: RuntimeRecorder) -> None:
        """建立仅属于当前 Session 的 Context 索引。"""
        self._recorder = recorder
        self._artifact_ids: list[str] = []

    def add(self, content: bytes, actor: ActorCall) -> Artifact:
        """加入一个新的 Context Artifact。"""
        artifact = self._recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.CONTEXT_ADD,
                artifact_type=ArtifactType.CONTEXT,
                content=content,
                actor=actor,
                origins=frozenset({actor.actor_id}),
                trust=TrustLevel.UNTRUSTED,
            )
        )
        self._artifact_ids.append(artifact.artifact_id)
        return artifact

    def read(self, artifact_id: str, actor: ActorCall) -> Artifact:
        """读取当前 Context 版本并生成新的派生版本。"""
        source = self._require_current(artifact_id)
        artifact = self._recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.CONTEXT_READ,
                artifact_type=ArtifactType.CONTEXT,
                content=self._recorder.read_content(artifact_id),
                actor=actor,
                input_artifact_ids=(artifact_id,),
                origins=source.observed_label.origins,
                trust=source.observed_label.trust,
                mime_type=source.mime_type,
            )
        )
        self._artifact_ids.append(artifact.artifact_id)
        return artifact

    def summarize(self, artifact_ids: tuple[str, ...], actor: ActorCall) -> Artifact:
        """按输入顺序连接内容，模拟确定性摘要转换。"""
        sources = tuple(self._require_current(artifact_id) for artifact_id in artifact_ids)
        content = b"\n".join(self._recorder.read_content(item.artifact_id) for item in sources)
        artifact = self._recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.CONTEXT_SUMMARIZE,
                artifact_type=ArtifactType.CONTEXT,
                content=content,
                actor=actor,
                input_artifact_ids=artifact_ids,
                origins=frozenset(
                    origin for item in sources for origin in item.observed_label.origins
                ),
                trust=TrustLevel.UNTRUSTED,
                mime_type="text/plain",
            )
        )
        self._artifact_ids.append(artifact.artifact_id)
        return artifact

    def _require_current(self, artifact_id: str) -> Artifact:
        if artifact_id not in self._artifact_ids:
            raise ArtifactContentError(artifact_id, "不属于当前 Session Context")
        return self._recorder.require_artifact(artifact_id)
