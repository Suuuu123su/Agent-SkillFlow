"""只读分析数据，逐条核对调度、阶段、运行和重放身份。"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t17.v2.configuration import canonical_digest
from skillflow.experiment.t17.v2.portable import recompute_core, redact_definition
from skillflow.experiment.t17.v2.replay_proof import build_replay_proof
from skillflow.experiment.t18.catalog_models import LocalCatalog
from skillflow.experiment.t18.controls import bind_matrix_controls, configured_scenario
from skillflow.experiment.t18.hiaa import HiaaTrial
from skillflow.experiment.t18.matrix import CoreCell, LocalMatrix
from skillflow.experiment.t18.preregistration import Preregistration
from skillflow.experiment.t18.replay import LocalReplay
from skillflow.experiment.t18.run_models import LocalCore, LocalPhase
from skillflow.experiment.t18.stage import load_inputs


@dataclass(frozen=True, slots=True)
class AnalysisData:
    """分析层可以读取真值，但不向正在运行的防御回传数据。"""

    phase: LocalPhase
    config: Preregistration
    matrix: LocalMatrix
    catalog: LocalCatalog
    scheduled: tuple[CoreCell, ...]
    cores: tuple[LocalCore, ...]
    replays: tuple[LocalReplay, ...]

    @property
    def complete(self) -> bool:
        """任务失败仍然完成，缺失记录才是不完整。"""
        return len(self.cores) == len(self.scheduled) and all(
            c.status == "completed" for c in self.cores
        )

    @property
    def evidence(self) -> tuple[str, ...]:
        """Run 身份将同种子下重复的局部 Artifact ID 消歧。"""
        return tuple(c.run_id for c in self.cores)

    def select(self, predicate: Callable[[CoreCell], bool]) -> "AnalysisData":
        """保留所选调度的原分母，不仅筛选成功记录。"""
        cells = tuple(c for c in self.scheduled if predicate(c))
        ids = {c.trial_id for c in cells}
        cores = tuple(c for c in self.cores if c.cell.trial_id in ids)
        return AnalysisData(
            self.phase,
            self.config,
            self.matrix,
            self.catalog,
            cells,
            cores,
            tuple(r for r in self.replays if r.trial_id in ids),
        )


def load_run(project: Path, directory: Path, *, verify: bool = True) -> AnalysisData:
    """从本地正式终态读取；不再打开模型或恢复实验。"""
    phase = LocalPhase.model_validate_json(
        (directory / "phase-contract.json").read_text(encoding="utf-8")
    )
    config, matrix, catalog = load_inputs(project, phase.domain)
    cores = tuple(
        LocalCore.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((directory / "terminals").glob("*.json"))
    )
    replays = tuple(
        LocalReplay.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((directory / "replay").glob("*/portable-replay.json"))
    )
    data = AnalysisData(phase, config, matrix, catalog, matrix.cores, cores, replays)
    validate_data(data, verify=verify)
    return data


def validate_data(data: AnalysisData, *, verify: bool) -> None:
    """公开事实可独立计算；禁止重复核心和跨阶段拼接。"""
    registered = (
        data.config.scripted if data.phase.domain == "scripted" else data.config.fake_reference
    )
    if (
        data.phase.domain != data.matrix.domain
        or data.phase.scheduled_core != len(data.matrix.cores)
        or registered != data.matrix
        or bind_matrix_controls(data.matrix, data.catalog)
        != data.config.hiaa_controls[data.phase.domain]
    ):
        raise ValueError("t18_report_shared_control_binding")
    phase_hash = canonical_digest(data.phase.model_dump(mode="json"))
    if canonical_digest(data.config.model_dump(mode="json")) != data.phase.preregistration_sha256:
        raise ValueError("t18_report_preregistration_binding")
    if (
        canonical_digest(data.matrix.model_dump(mode="json")) != data.phase.matrix_sha256
        or canonical_digest(data.catalog.model_dump(mode="json")) != data.phase.catalog_sha256
    ):
        raise ValueError("t18_report_input_commitment")
    skills = {s.skill_variant_id: s for s in data.catalog.skills}
    scheduled = {c.trial_id: c for c in data.matrix.cores}
    if len({c.run_id for c in data.cores}) != len(data.cores) or len(
        {c.cell.trial_id for c in data.cores}
    ) != len(data.cores):
        raise ValueError("t18_report_duplicate_core")
    for core in data.cores:
        skill = skills[core.cell.skill_variant_id]
        if core.data is not None and (
            core.data.task_contract != skill.task_contract
            or core.data.analysis_definition
            != redact_definition(configured_scenario(skill, core.cell))
        ):
            raise ValueError("t18_report_task_contract_binding")
        if (
            core.phase_contract_sha256 != phase_hash
            or core.domain != data.phase.domain
            or scheduled.get(core.cell.trial_id) != core.cell
        ):
            raise ValueError("t18_report_phase_binding")
        if verify and core.data is not None and recompute_core(core.data) != core.data.proof:
            raise ValueError("t18_report_core_recompute_mismatch")
    _validate_replays(data, verify=verify)


def _validate_replays(data: AnalysisData, *, verify: bool) -> None:
    by_trial = {c.cell.trial_id: c for c in data.cores}
    if (
        len({p.pair_id for p in data.replays}) != len(data.replays)
        or len(data.replays) > data.phase.max_replay_pairs
    ):
        raise ValueError("t18_report_replay_count")
    for replay in data.replays:
        source_core = by_trial.get(replay.trial_id)
        if (
            source_core is None
            or source_core.run_id != replay.source_run_id
            or replay.domain != data.phase.domain
            or replay.pair_id not in source_core.replay_pair_ids
        ):
            raise ValueError("t18_report_replay_binding")
        proof = replay.proof
        if (
            source_core.data is None
            or proof.source.run_id != source_core.run_id
            or proof.source.events != source_core.data.facts.events[: len(proof.source.events)]
        ):
            raise ValueError("t18_report_replay_core_prefix")
        if (
            verify
            and build_replay_proof(
                proof.source, proof.original, proof.neutral, proof.selector, proof.manifest
            )
            != proof
        ):
            raise ValueError("t18_report_replay_recompute_mismatch")
    if {p.pair_id for p in data.replays} != {p for c in data.cores for p in c.replay_pair_ids}:
        raise ValueError("t18_report_missing_replay")


def hiaa_trials(data: AnalysisData) -> tuple[HiaaTrial, ...]:
    """目标命中由正常任务证据中的独立风险选择器读取。"""
    result = []
    for core in data.cores:
        behaviors = {d.behavior for d in core.decisions}
        complete = core.status == "completed" and core.data is not None
        result.append(
            HiaaTrial(
                trial_id=core.cell.trial_id,
                run_id=core.run_id,
                domain=core.domain,
                complete=complete,
                valid=complete
                and not behaviors.intersection({"refusal", "no_call", "schema_rejection"}),
                target_effect=bool(core.data and core.data.proof.task.risk_effect_ids),
                evidence_ids=(
                    core.run_id,
                    *(core.data.proof.task.evidence_ids if core.data else ()),
                ),
                refusal="refusal" in behaviors,
                no_call="no_call" in behaviors,
                schema_failure="schema_rejection" in behaviors,
                task_failure=bool(core.data and not core.data.proof.task.task_success),
            )
        )
    return tuple(result)
