"""续跑证据为显式来源索引；不改旧记录，联合日志明确标为派生记录。"""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from t17_continue_models import (
    CompositeRawManifest,
    EventLineage,
    SourceIndex,
    SourceUnit,
    terminal_path,
)

from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.dataset_writing import DatasetWriter
from skillflow.experiment.t17.v2.frozen import file_digest, inside
from skillflow.experiment.t17.v2.journal import _hash_event, read_journal, verify_journal
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.phase_gate import build_gate
from skillflow.experiment.t17.v2.phase_validation import validate_structured_stage
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    PhaseContract,
    ReplayTerminal,
    StageResult,
)
from skillflow.experiment.t17.v2.stage import StageSetup


def join_events(
    parts: tuple[tuple[str, tuple[ApiUsageEvent, ...]], ...],
    *,
    allowed_phases: frozenset[str] = frozenset(),
) -> tuple[tuple[ApiUsageEvent, ...], tuple[EventLineage, ...]]:
    """只重编号和累计显示额度；原始事件完整保留并逐行关联，不伪造响应。"""
    joined: list[ApiUsageEvent] = []
    lineage: list[EventLineage] = []
    attempt_number = 0
    reserved = Decimal(0)
    for source, events in parts:
        if not events:
            continue
        if events[0].event_type != "unit_start":
            raise ValueError("continuation_partial_unit_journal")
        base = events[0].total_reserved_usd
        indices: dict[int, int] = {}
        for event in events:
            if event.event_type == "attempt":
                attempt_number += 1
                indices[event.attempt_index] = attempt_number
            index = (
                attempt_number if event.event_type == "unit_start" else indices[event.attempt_index]
            )
            derived = event.model_copy(
                update={
                    "sequence": len(joined) + 1,
                    "attempt_index": index,
                    "total_reserved_usd": reserved + event.total_reserved_usd - base,
                    "previous_sha256": joined[-1].event_sha256 if joined else None,
                }
            )
            derived = derived.model_copy(update={"event_sha256": _hash_event(derived)})
            lineage.append(
                EventLineage(
                    sequence=derived.sequence,
                    source_raw=source,
                    source_sequence=event.sequence,
                    source_event_sha256=event.event_sha256,
                )
            )
            joined.append(derived)
        reserved = joined[-1].total_reserved_usd
    return verify_journal(tuple(joined), allowed_phases=allowed_phases), tuple(lineage)


def read_sources(
    root: Path, units: tuple[SourceUnit, ...], *, allowed_phases: frozenset[str] = frozenset()
) -> tuple[
    tuple[CoreTerminal, ...],
    tuple[ReplayTerminal, ...],
    tuple[ApiUsageEvent, ...],
    tuple[EventLineage, ...],
]:
    """从每个原始来源读取选中的事实与账本，保留事件关联。"""
    cores: list[CoreTerminal] = []
    replays: list[ReplayTerminal] = []
    identifiers: dict[str, set[str]] = defaultdict(set)
    for source in units:
        path = terminal_path(root, source)
        if file_digest(path) != source.terminal_file:
            raise ValueError("continuation_selected_terminal_changed")
        if source.kind == "core":
            cores.append(read_model(path, CoreTerminal))
        else:
            replays.append(read_model(path, ReplayTerminal))
        identifiers[source.source_raw].add(source.unit_id)
    parts = tuple(
        (
            raw,
            tuple(
                event
                for event in read_journal(inside(root, raw) / "api-usage.jsonl")
                if event.unit_id in selected
            ),
        )
        for raw, selected in identifiers.items()
    )
    events, lineage = join_events(parts, allowed_phases=allowed_phases)
    return tuple(cores), tuple(replays), events, lineage


def write_evidence(setup: StageSetup, index: SourceIndex, directory: Path) -> LoadedStage:
    """写入新来源集合并复算阶段门，失败原始文件不回填。"""
    root = setup.project_root
    phase = setup.approved_phase
    if phase is None:
        raise ValueError("continuation_phase_missing")
    origins = {
        model_digest(p): p
        for raw in {u.source_raw for u in index.units}
        for p in (read_model(inside(root, raw) / "phase-contract.json", PhaseContract),)
        if p != phase
    }
    source_phases = tuple(origins.values())
    allowed = frozenset((model_digest(phase), *origins))
    cores, replays, events, lineage = read_sources(root, index.units, allowed_phases=allowed)
    gate = build_gate(
        phase,
        setup.matrix,
        AnalysisGroup(setup.configuration, cores, replays),
        events,
        source_phases=source_phases,
    )
    writer = DatasetWriter(root, directory)
    writer.model("selection.json", index)
    writer.model("configuration.json", setup.configuration)
    writer.model("matrix.json", setup.matrix)
    writer.model("phase-contract.json", phase)
    writer.model("phase-gate.json", gate)
    writer.rows("api-usage.jsonl", events, ApiUsageEvent)
    writer.rows("api-event-lineage.jsonl", lineage, EventLineage)
    manifest = CompositeRawManifest(
        source_index=index,
        files={name: info.content for name, info in writer.files.items()},
    )
    writer.model("continuation-manifest.json", manifest)
    loaded = LoadedStage(
        configuration=setup.configuration,
        matrix=setup.matrix,
        result=StageResult(
            phase=phase, cores=cores, replays=replays, gate=gate, source_phases=source_phases
        ),
        raw_relative_path=directory.relative_to(root).as_posix(),
        raw_manifest=file_digest(directory / "continuation-manifest.json"),
        raw_files={name: info.content for name, info in writer.files.items()},
        api_usage=events,
    )
    if gate.passed:
        validate_structured_stage(loaded)
    return loaded
