"""临时 Workspace 文件插桩。"""

from pathlib import Path

from skillflow.instrumentation.errors import WorkspaceEscapeError, WorkspaceResourceError
from skillflow.models.enums import ArtifactType, EventType, TrustLevel
from skillflow.models.provenance import Artifact
from skillflow.models.resources import ResourceRef
from skillflow.runtime.session import ActorCall, ArtifactEmission, RuntimeRecorder


class InstrumentedFile:
    """只能访问注入 Workspace 根目录的文件代理。"""

    def __init__(self, workspace_root: Path, recorder: RuntimeRecorder) -> None:
        """固定并规范化本次测试的唯一 Workspace 根。"""
        self._workspace_root = workspace_root.resolve()
        self._recorder = recorder

    def read(self, resource: ResourceRef, actor: ActorCall) -> Artifact:
        """读取 Workspace 文件并记录 FILE_READ。"""
        path = self._resolve(resource)
        try:
            content = path.read_bytes()
        except OSError as error:
            reason = error.strerror if error.strerror is not None else error.__class__.__name__
            raise WorkspaceResourceError(resource.root, reason) from error
        return self._recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.FILE_READ,
                artifact_type=ArtifactType.FILE,
                content=content,
                actor=actor,
                origins=frozenset({resource.root}),
                trust=TrustLevel.USER,
                mime_type="application/octet-stream",
                metadata={"resource": resource.root},
            )
        )

    def write(self, resource: ResourceRef, content: bytes, actor: ActorCall) -> Artifact:
        """只在 Workspace 内写文件并记录 FILE_WRITE。"""
        path = self._resolve(resource)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(content)
        except OSError as error:
            reason = error.strerror if error.strerror is not None else error.__class__.__name__
            raise WorkspaceResourceError(resource.root, reason) from error
        return self._recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.FILE_WRITE,
                artifact_type=ArtifactType.FILE,
                content=content,
                actor=actor,
                origins=frozenset({actor.actor_id}),
                trust=TrustLevel.UNTRUSTED,
                metadata={"resource": resource.root},
            )
        )

    def _resolve(self, resource: ResourceRef) -> Path:
        prefix = "workspace:/"
        if not resource.root.startswith(prefix):
            raise WorkspaceResourceError(resource.root, "只允许 workspace: 资源")
        candidate = (self._workspace_root / resource.root.removeprefix(prefix)).resolve()
        if not candidate.is_relative_to(self._workspace_root):
            raise WorkspaceEscapeError(resource.root)
        return candidate
