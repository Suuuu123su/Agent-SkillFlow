"""只凭持久化开始记录区分中断与未运行，不能按文件缺失猜完成状态。"""

from pathlib import Path
from typing import TypeVar

from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Matrix
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    PhaseContract,
    ReplayTerminal,
    TerminalStatus,
    UnitIdentity,
    UnitUsage,
)
from skillflow.experiment.t17.v2.stage_contract import unit_identity
from skillflow.experiment.t17.v2.unit_execution import compact_id
from skillflow.experiment.t17.v2.usage_validation import journal_unit_usage

TerminalT = TypeVar("TerminalT", CoreTerminal, ReplayTerminal)


def interrupted_terminals(
    phase: PhaseContract, matrix: V2Matrix, raw: Path, reason: str
) -> tuple[tuple[CoreTerminal | ReplayTerminal, ...], tuple[str, ...]]:
    """保留已有终态；没有可信开始证据且日志可读才写为未运行。"""
    events, readable = _events(raw, phase)
    records: list[CoreTerminal | ReplayTerminal] = []
    preserved: list[str] = []
    for trial in matrix.trials:
        identity = unit_identity(phase, matrix, trial, trial.trial_id)
        core = _existing(raw, identity, CoreTerminal)
        if core is None:
            usage, status = _state(raw / "core", identity, events, readable)
            records.append(
                CoreTerminal(identity=identity, status=status, reason=reason, usage=usage)
            )
        else:
            preserved.append(trial.trial_id)
        for alias, pair_id in trial.replay_pair_ids.items():
            identity = unit_identity(phase, matrix, trial, pair_id)
            if _existing(raw, identity, ReplayTerminal) is not None:
                preserved.append(pair_id)
                continue
            usage, status = _state(raw / "replay", identity, events, readable)
            records.append(
                ReplayTerminal(
                    identity=identity,
                    source_core_run_id=None if core is None else core.run_id,
                    target_alias=alias,
                    status=status,
                    reason=reason,
                    usage=usage,
                )
            )
    return tuple(records), tuple(preserved)


def _events(raw: Path, phase: PhaseContract) -> tuple[tuple[ApiUsageEvent, ...], bool]:
    try:
        path = raw / "api-usage.jsonl"
        events = read_journal(path) if path.is_file() else ()
    except (ValueError, OSError):
        return (), False
    if any(
        e.phase_contract_sha256 != model_digest(phase) or e.matrix_sha256 != phase.matrix_sha256
        for e in events
    ):
        return (), False
    return events, True


def _state(
    kind_dir: Path, identity: UnitIdentity, events: tuple[ApiUsageEvent, ...], readable: bool
) -> tuple[UnitUsage, TerminalStatus]:
    rows = tuple(e for e in events if e.unit_id == identity.unit_id)
    started = bool(rows) or (kind_dir / compact_id(identity.unit_id)).exists()
    usage = (
        journal_unit_usage(rows)
        if readable
        else UnitUsage(
            complete=False,
            missing_reason="journal_unreadable_start_state_unknown",
        )
    )
    return usage, "infrastructure_invalid" if started or not readable else "not_run"


def _existing(raw: Path, identity: UnitIdentity, model: type[TerminalT]) -> TerminalT | None:
    try:
        value = read_model(raw / "terminals" / (compact_id(identity.unit_id) + ".json"), model)
    except (ValueError, OSError):
        return None
    return value if value.identity == identity else None
