"""从被测 EventStore 与 Observed 标签投影脱敏 Trace。"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, TypeAlias

from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import EventType
from skillflow.store.errors import StoreIntegrityError
from skillflow.store.event_store import EventStore
from skillflow.trace.contracts import ParentRelation, TraceParent, TraceValueType
from skillflow.trace.jsonl import write_jsonl

ARTIFACT_RELATIONS: Final = {
    EventType.CONTEXT_ADD: ParentRelation.COPY,
    EventType.CONTEXT_READ: ParentRelation.COPY,
    EventType.CONTEXT_SUMMARIZE: ParentRelation.DERIVE,
    EventType.MEMORY_WRITE: ParentRelation.WRITE,
    EventType.MEMORY_READ: ParentRelation.LOAD,
    EventType.FILE_READ: ParentRelation.LOAD,
    EventType.FILE_WRITE: ParentRelation.WRITE,
    EventType.SKILL_RETURN: ParentRelation.INVOKE,
    EventType.TOOL_CALL_REQUEST: ParentRelation.INVOKE,
    EventType.TOOL_CALL_RESULT: ParentRelation.INVOKE,
    EventType.ARTIFACT_REGISTER: ParentRelation.COPY,
    EventType.ARTIFACT_DERIVE: ParentRelation.DERIVE,
}


class ObservedArtifactTrace(StrictModel):
    """Observed Plane 中一个不可变 Artifact 的脱敏投影。"""

    plane: Literal["observed"] = "observed"
    record_type: Literal["artifact"] = "artifact"
    run_id: NonEmptyStr
    artifact_id: NonEmptyStr
    value_type: TraceValueType
    event_id: NonEmptyStr
    aliases: tuple[NonEmptyStr, ...] = ()
    observed_data: tuple[NonEmptyStr, ...]
    parents: tuple[TraceParent, ...]


class ObservedEffectTrace(StrictModel):
    """Observed Plane 对实际 Receipt Effect 的脱敏投影。"""

    plane: Literal["observed"] = "observed"
    record_type: Literal["effect"] = "effect"
    run_id: NonEmptyStr
    effect_id: NonEmptyStr
    action_id: NonEmptyStr
    actor_id: NonEmptyStr
    task_id: NonEmptyStr
    session_id: NonEmptyStr
    call_id: NonEmptyStr
    timestamp: datetime
    effect: CapabilityEffect
    observed_auth: bool
    observed_effect: bool
    decision_id: NonEmptyStr
    receipt_id: NonEmptyStr
    parents: tuple[TraceParent, ...]


ObservedTraceRecord: TypeAlias = ObservedArtifactTrace | ObservedEffectTrace


@dataclass(frozen=True, slots=True)
class ObservedRunInput:
    """Observed Writer 唯一允许读取的运行事实。"""

    run_id: str
    store: EventStore
    receipts: tuple[ToolReceipt, ...]
    artifact_aliases: Mapping[str, tuple[str, ...]]


class ObservedTraceWriter:
    """为一次 Run 创建 observed-trace.jsonl。"""

    def __init__(self, destination: Path) -> None:
        """固定一个不可覆盖的目标文件。"""
        self._destination = destination

    def write(self, run: ObservedRunInput) -> tuple[ObservedTraceRecord, ...]:
        """投影 Artifact/Effect，不读取 Blob 或任意 Event metadata。"""
        records: tuple[ObservedTraceRecord, ...] = (
            *self._artifacts(run),
            *self._effects(run),
        )
        write_jsonl(self._destination, records)
        return records

    @staticmethod
    def _artifacts(run: ObservedRunInput) -> tuple[ObservedArtifactTrace, ...]:
        records: list[ObservedArtifactTrace] = []
        for event in run.store.iter_run_events(run.run_id):
            if not event.output_artifact_ids:
                continue
            try:
                relation = ARTIFACT_RELATIONS[event.event_type]
            except KeyError as error:
                raise StoreIntegrityError(
                    "write_observed_trace",
                    f"输出 Event 缺少父关系映射：{event.event_type.value}",
                ) from error
            for artifact_id in event.output_artifact_ids:
                artifact = run.store.get_artifact(artifact_id)
                if artifact is None:
                    raise StoreIntegrityError(
                        "write_observed_trace",
                        f"Artifact 不存在：{artifact_id}",
                    )
                records.append(
                    ObservedArtifactTrace(
                        run_id=run.run_id,
                        artifact_id=artifact_id,
                        value_type=TraceValueType(artifact.artifact_type.value),
                        event_id=event.event_id,
                        aliases=run.artifact_aliases.get(artifact_id, ()),
                        observed_data=tuple(sorted(artifact.observed_label.origins)),
                        parents=tuple(
                            TraceParent(parent_id=parent_id, relation=relation)
                            for parent_id in sorted(artifact.observed_label.parent_artifact_ids)
                        ),
                    )
                )
        return tuple(records)

    @staticmethod
    def _effects(run: ObservedRunInput) -> tuple[ObservedEffectTrace, ...]:
        records: list[ObservedEffectTrace] = []
        for receipt in run.receipts:
            effect = run.store.get_effect(receipt.effect_id)
            request = run.store.get_event(receipt.request_event_id)
            if effect is None or request is None:
                raise StoreIntegrityError(
                    "write_observed_trace",
                    f"Receipt 引用缺失：{receipt.receipt_id}",
                )
            decision = run.store.get_decision(effect.decision_id)
            if decision is None:
                raise StoreIntegrityError(
                    "write_observed_trace",
                    f"Decision 不存在：{effect.decision_id}",
                )
            if request.call_id is None:
                raise StoreIntegrityError(
                    "write_observed_trace",
                    f"Tool 请求缺少 call_id：{request.event_id}",
                )
            records.append(
                ObservedEffectTrace(
                    run_id=run.run_id,
                    effect_id=effect.effect_id,
                    action_id=receipt.action_id,
                    actor_id=request.actor_id,
                    task_id=request.task_id,
                    session_id=request.session_id,
                    call_id=request.call_id,
                    timestamp=receipt.timestamp,
                    effect=effect.effect,
                    observed_auth=decision.authorized,
                    observed_effect=effect.executed,
                    decision_id=decision.decision_id,
                    receipt_id=receipt.receipt_id,
                    parents=(
                        TraceParent(
                            parent_id=receipt.argument_artifact_id,
                            relation=ParentRelation.INVOKE,
                        ),
                    ),
                )
            )
        return tuple(records)
