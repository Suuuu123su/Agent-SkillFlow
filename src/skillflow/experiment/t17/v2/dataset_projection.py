"""从核心与回放事实机械展开任务、效果和来源表。"""

from collections.abc import Iterator
from typing import Literal

from skillflow.experiment.t17.v2.dataset_rows import (
    ApiUsageRow,
    EffectReceiptRow,
    ProvenanceRow,
    TaskEvidenceRow,
)
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.portable_models import PortableRun
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal, UnitIdentity
from skillflow.oracle.models import OracleArtifactTrace


def task_rows(stages: tuple[LoadedStage, ...]) -> Iterator[TaskEvidenceRow]:
    """每条可评估核心任务一条，失败任务不捏造成功证据。"""
    for stage in stages:
        for core in stage.result.cores:
            if core.data is not None:
                yield TaskEvidenceRow(
                    identity=core.identity,
                    run_id=core.data.facts.run_id,
                    session_ids=core.data.proof.task.completed_session_ids,
                    evidence=core.data.proof.task,
                )


def effect_rows(stages: tuple[LoadedStage, ...]) -> Iterator[EffectReceiptRow]:
    """原始与中和分支分别保留，不能混入核心分母。"""
    for stage in stages:
        for core in stage.result.cores:
            if core.data is not None:
                yield from _effects(core.identity, core.data.facts, "core", frozenset())
        for replay in stage.result.replays:
            proof = replay.proof
            if proof is not None:
                prefix = frozenset(e.effect_id for e in proof.source.effects)
                yield from _effects(replay.identity, proof.original, "original", prefix)
                yield from _effects(replay.identity, proof.neutral, "neutral", prefix)


def _effects(
    identity: UnitIdentity,
    facts: PortableRun,
    branch: Literal["core", "original", "neutral"],
    prefix: frozenset[str],
) -> Iterator[EffectReceiptRow]:
    events = {e.event_id: e for e in facts.events}
    receipts = {r.effect_id: r for r in facts.receipts}
    for effect in facts.effects:
        if effect.executed:
            yield EffectReceiptRow(
                identity=identity,
                run_id=facts.run_id,
                session_id=events[effect.request_event_id].session_id,
                branch=branch,
                in_replay_prefix=effect.effect_id in prefix,
                effect=effect,
                receipt=receipts[effect.effect_id],
            )


def provenance_rows(stages: tuple[LoadedStage, ...]) -> Iterator[ProvenanceRow]:
    """所有核心值均有观察侧；真实来源按独立记录绑定。"""
    for stage in stages:
        for core in stage.result.cores:
            if core.data is None:
                continue
            oracle = {
                o.artifact_id: o for o in core.data.oracle if isinstance(o, OracleArtifactTrace)
            }
            for artifact in core.data.facts.artifacts:
                yield ProvenanceRow(
                    identity=core.identity,
                    run_id=core.data.facts.run_id,
                    session_id=artifact.observed_label.created_session_id,
                    artifact=artifact,
                    oracle=oracle.get(artifact.artifact_id),
                )


def usage_rows(stages: tuple[LoadedStage, ...]) -> Iterator[ApiUsageRow]:
    """逐日志行补上冻结单元身份，不公开 HTTP 请求头。"""
    for stage in stages:
        records: tuple[CoreTerminal | ReplayTerminal, ...] = (
            *stage.result.cores,
            *stage.result.replays,
        )
        identities = {r.identity.unit_id: r.identity for r in records}
        for event in stage.api_usage:
            yield ApiUsageRow(identity=identities[event.unit_id], event=event)
