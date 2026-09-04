"""独立尝试的调度；失败与未开始单元均留下结构化终态。"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.reference_backend import ReferenceModelClient
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.api_models import AccountingClient, ApiUsageEvent
from skillflow.experiment.t17.v2.campaign_models import StageProgress
from skillflow.experiment.t17.v2.campaign_usage import progress
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.frozen import FrozenFile, inside
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.phase_gate import build_gate
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    PhaseContract,
    ReplayTerminal,
    StageResult,
    V2Domain,
)
from skillflow.experiment.t17.v2.stage_contract import freeze_phase
from skillflow.experiment.t17.v2.stage_units import UnitScheduler, failure_category
from skillflow.experiment.t17.v2.unit_execution import ExecutionContext, compact_id, file_inventory
from skillflow.models.base import NonEmptyStr, StrictModel


@dataclass(frozen=True, slots=True)
class StageSetup:
    """调用方显式选择零费用验证或获批真实域。"""

    project_root: Path
    output: Path
    configuration: V2Configuration
    matrix: V2Matrix
    domain: V2Domain
    client: ReferenceModelClient | None
    observer: Callable[[StageProgress], None] | None = None
    approved_phase: PhaseContract | None = None


class StageRawManifest(StrictModel):
    """完整原始记录仍在本地，只公开相对路径、记录数和哈希。"""

    phase_contract_sha256: NonEmptyStr
    files: dict[NonEmptyStr, FrozenFile] = Field(default_factory=dict)


def run_stage(setup: StageSetup) -> StageResult:
    """不覆盖、不续填旧尝试；所有可预见模型失败均在可信运行时终态化。"""
    root = setup.project_root.resolve()
    output = inside(root, setup.output.resolve().relative_to(root).as_posix())
    phase, accounting = _prepare_phase(setup)
    output.mkdir(parents=True, exist_ok=False)
    write_checked_json(output / "phase-contract.json", phase)
    write_checked_json(output / "configuration.json", setup.configuration)
    write_checked_json(output / "matrix.json", setup.matrix)
    context = ExecutionContext(root, output, setup.configuration, setup.matrix, phase, setup.client)
    scheduler = UnitScheduler(context, accounting)
    if accounting is not None:
        try:
            accounting.open_phase(output, phase)
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- 请求前失败也逐条终态化。
            scheduler.startup_failure = failure_category(error)
    cores: list[CoreTerminal] = []
    replays: list[ReplayTerminal] = []
    for trial in setup.matrix.trials:
        core, execution = scheduler.run_core(trial)
        cores.append(core)
        _write_terminal(output, core)
        if setup.observer is not None:
            setup.observer(progress(phase, cores, replays))
        for alias in trial.replay_pair_ids:
            replay = scheduler.run_replay(trial, core, execution, alias)
            replays.append(replay)
            _write_terminal(output, replay)
            if setup.observer is not None:
                setup.observer(progress(phase, cores, replays))
    usage, readable = _load_usage(output)
    gate = build_gate(
        phase, setup.matrix, AnalysisGroup(setup.configuration, tuple(cores), tuple(replays)), usage
    )
    if not readable:
        gate = gate.model_copy(
            update={
                "passed": False,
                "usage_complete": False,
                "failures": (*gate.failures, "usage_journal_unreadable"),
            }
        )
    result = StageResult(
        phase=phase,
        cores=tuple(cores),
        replays=tuple(replays),
        gate=gate,
    )
    write_checked_json(output / "phase-gate.json", result.gate)
    write_checked_json(
        output / "raw-manifest.json",
        StageRawManifest(
            phase_contract_sha256=model_digest(phase), files=file_inventory(output, output)
        ),
    )
    return result


def _prepare_phase(setup: StageSetup) -> tuple[PhaseContract, AccountingClient | None]:
    phase = freeze_phase(
        setup.project_root.resolve(), setup.configuration, setup.matrix, setup.domain
    )
    if (setup.domain == "live_reference" and setup.approved_phase is None) or (
        setup.approved_phase is not None and setup.approved_phase != phase
    ):
        raise ValueError("v2_approved_phase_missing_or_drift")
    accounting: AccountingClient | None = (
        setup.client if isinstance(setup.client, AccountingClient) else None
    )
    if setup.domain == "live_reference" and (
        accounting is None or not accounting.authorized_for(phase.matrix_sha256)
    ):
        raise ValueError("v2_live_budget_not_authorized")
    if (setup.domain == "scripted") != (setup.client is None):
        raise ValueError("v2_execution_domain_client_mismatch")
    return phase, accounting


def _load_usage(output: Path) -> tuple[tuple[ApiUsageEvent, ...], bool]:
    try:
        path = output / "api-usage.jsonl"
        return (read_journal(path) if path.is_file() else ()), True
    except (ValueError, OSError):
        return (), False


def _write_terminal(output: Path, record: CoreTerminal | ReplayTerminal) -> None:
    directory = output / "terminals"
    directory.mkdir(exist_ok=True)
    write_checked_json(directory / (compact_id(record.identity.unit_id) + ".json"), record)
