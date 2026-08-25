"""Mock Harness checkpoint 的冻结合同与规范化哈希。"""

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel, JsonValue, TypeAdapter

from skillflow.instrumentation.context_proxy import ContextStateSnapshot
from skillflow.instrumentation.memory_proxy import MemoryStateSnapshot
from skillflow.instrumentation.mock_tools import MockNetworkRecord, MockShellRecord
from skillflow.instrumentation.skill_proxy import SkillRuntimeSnapshot, SkillStateSnapshot
from skillflow.models.enums import ProvenanceMode
from skillflow.runtime.determinism import DeterministicIdSnapshot, VirtualClockSnapshot
from skillflow.runtime.workspace_checkpoint import WorkspaceSnapshot
from skillflow.store.checkpoint import RunStoreSnapshot
from skillflow.store.errors import StoreIntegrityError

JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


@dataclass(frozen=True, slots=True)
class HarnessCheckpoint:
    """一个静止 step 边界的完整逻辑状态。"""

    checkpoint_id: str
    source_run_id: str
    task_id: str
    session_id: str
    provenance_mode: ProvenanceMode
    store: RunStoreSnapshot
    workspace: WorkspaceSnapshot
    context: ContextStateSnapshot
    memory: MemoryStateSnapshot
    skill_state: SkillStateSnapshot
    skills: SkillRuntimeSnapshot
    network_records: tuple[MockNetworkRecord, ...]
    shell_records: tuple[MockShellRecord, ...]
    clock: VirtualClockSnapshot
    ids: DeterministicIdSnapshot
    initial_grants_registered: bool
    prefix_hash: str
    state_hash: str

    @property
    def event_count(self) -> int:
        """返回冻结前缀中的 Event 数。"""
        return len(self.store.envelopes)


@dataclass(frozen=True, slots=True)
class HarnessCheckpointParts:
    """计算 checkpoint 前由 Harness 显式采集的全部组件。"""

    source_run_id: str
    task_id: str
    session_id: str
    provenance_mode: ProvenanceMode
    store: RunStoreSnapshot
    workspace: WorkspaceSnapshot
    context: ContextStateSnapshot
    memory: MemoryStateSnapshot
    skill_state: SkillStateSnapshot
    skills: SkillRuntimeSnapshot
    network_records: tuple[MockNetworkRecord, ...]
    shell_records: tuple[MockShellRecord, ...]
    clock: VirtualClockSnapshot
    ids: DeterministicIdSnapshot
    initial_grants_registered: bool


def create_harness_checkpoint(parts: HarnessCheckpointParts) -> HarnessCheckpoint:
    """校验私有内容后生成不含宿主路径和 run_id 的规范化哈希。"""
    if parts.skills.active_invocation_event_ids:
        raise StoreIntegrityError("capture_checkpoint", "存在未完成的 Skill 调用")
    _verify_private_content(parts.store, parts.workspace)
    prefix_hash = _hash_payload(_prefix_payload(parts.store))
    state_hash = _hash_payload(_state_payload(parts, prefix_hash))
    return HarnessCheckpoint(
        checkpoint_id=f"checkpoint-{state_hash[:16]}",
        source_run_id=parts.source_run_id,
        task_id=parts.task_id,
        session_id=parts.session_id,
        provenance_mode=parts.provenance_mode,
        store=parts.store,
        workspace=parts.workspace,
        context=parts.context,
        memory=parts.memory,
        skill_state=parts.skill_state,
        skills=parts.skills,
        network_records=parts.network_records,
        shell_records=parts.shell_records,
        clock=parts.clock,
        ids=parts.ids,
        initial_grants_registered=parts.initial_grants_registered,
        prefix_hash=prefix_hash,
        state_hash=state_hash,
    )


def verify_harness_checkpoint(checkpoint: HarnessCheckpoint) -> None:
    """在 restore 前重新验证内容摘要和两级哈希。"""
    parts = HarnessCheckpointParts(
        source_run_id=checkpoint.source_run_id,
        task_id=checkpoint.task_id,
        session_id=checkpoint.session_id,
        provenance_mode=checkpoint.provenance_mode,
        store=checkpoint.store,
        workspace=checkpoint.workspace,
        context=checkpoint.context,
        memory=checkpoint.memory,
        skill_state=checkpoint.skill_state,
        skills=checkpoint.skills,
        network_records=checkpoint.network_records,
        shell_records=checkpoint.shell_records,
        clock=checkpoint.clock,
        ids=checkpoint.ids,
        initial_grants_registered=checkpoint.initial_grants_registered,
    )
    rebuilt = create_harness_checkpoint(parts)
    if (
        rebuilt.checkpoint_id != checkpoint.checkpoint_id
        or rebuilt.prefix_hash != checkpoint.prefix_hash
        or rebuilt.state_hash != checkpoint.state_hash
    ):
        raise StoreIntegrityError("restore_checkpoint", "checkpoint 哈希不一致")


def _prefix_payload(snapshot: RunStoreSnapshot) -> JsonValue:
    envelopes: list[dict[str, JsonValue]] = []
    for envelope in snapshot.envelopes:
        event = envelope.event.model_dump(mode="json")
        event["run_id"] = "<branch-run>"
        revocation = envelope.revocation
        envelopes.append(
            {
                "event": event,
                "decision": _model_payload(envelope.decision),
                "effect": _model_payload(envelope.effect),
                "grant": _model_payload(envelope.grant),
                "revocation": (
                    None
                    if revocation is None
                    else {
                        "revocation_id": revocation.revocation_id,
                        "target_kind": revocation.target_kind.value,
                        "target_id": revocation.target_id,
                        "event_id": revocation.event_id,
                        "timestamp": revocation.timestamp.isoformat(),
                    }
                ),
            }
        )
    artifacts = [item.artifact.model_dump(mode="json") for item in snapshot.artifacts]
    heads = [
        {
            "key": head.key,
            "artifact_id": head.artifact_id,
            "session_id": head.session_id,
            "updated_event_id": head.updated_event_id,
        }
        for head in snapshot.memory_heads
    ]
    return JSON_VALUE_ADAPTER.validate_python(
        {"artifacts": artifacts, "envelopes": envelopes, "memory_heads": heads}
    )


def _state_payload(parts: HarnessCheckpointParts, prefix_hash: str) -> JsonValue:
    return JSON_VALUE_ADAPTER.validate_python(
        {
            "prefix_hash": prefix_hash,
            "task_id": parts.task_id,
            "session_id": parts.session_id,
            "provenance_mode": parts.provenance_mode.value,
            "context": list(parts.context.artifact_ids),
            "memory": [list(entry) for entry in parts.memory.entries],
            "skill_bindings": [
                [binding.skill_id, binding.implementation.root]
                for binding in parts.skill_state.bindings
            ],
            "revoked_skills": list(parts.skill_state.revoked_skill_ids),
            "loaded_skills": list(parts.skills.loaded_skill_ids),
            "network": [
                [record.effect_id, record.sink.root, record.source_artifact_id]
                for record in parts.network_records
            ],
            "shell": [[record.effect_id, list(record.command)] for record in parts.shell_records],
            "clock": parts.clock.current.isoformat(),
            "id_seed": parts.ids.seed,
            "id_counters": [list(counter) for counter in parts.ids.counters],
            "initial_grants_registered": parts.initial_grants_registered,
            "workspace": [
                [item.relative_path, item.content_hash, item.content_length]
                for item in parts.workspace.files
            ],
        }
    )


def _model_payload(model: BaseModel | None) -> JsonValue:
    return (
        None if model is None else JSON_VALUE_ADAPTER.validate_python(model.model_dump(mode="json"))
    )


def _hash_payload(payload: JsonValue) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _verify_private_content(
    store: RunStoreSnapshot,
    workspace: WorkspaceSnapshot,
) -> None:
    for artifact_item in store.artifacts:
        valid = (
            len(artifact_item.content) == artifact_item.artifact.content_length
            and hashlib.sha256(artifact_item.content).hexdigest()
            == artifact_item.artifact.content_hash
        )
        if not valid:
            raise StoreIntegrityError(
                "checkpoint",
                f"Artifact 内容损坏：{artifact_item.artifact.artifact_id}",
            )
    for workspace_item in workspace.files:
        valid = (
            len(workspace_item.content) == workspace_item.content_length
            and hashlib.sha256(workspace_item.content).hexdigest() == workspace_item.content_hash
        )
        if not valid:
            raise StoreIntegrityError(
                "checkpoint",
                f"Workspace 内容损坏：{workspace_item.relative_path}",
            )
