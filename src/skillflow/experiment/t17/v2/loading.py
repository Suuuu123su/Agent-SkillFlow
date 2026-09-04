"""只读装载一个不可变尝试，逐条复核哈希和指标输入，不继续旧运行。"""

from pathlib import Path
from typing import TypeVar

from skillflow.experiment.inputs import apply_variant, namespace_grants
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.binding import validate_core_binding, validate_replay_binding
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.frozen import file_digest, inside, verify_files
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.phase_gate import build_gate
from skillflow.experiment.t17.v2.portable import redact_definition
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    PhaseContract,
    PhaseGate,
    ReplayTerminal,
    StageResult,
)
from skillflow.experiment.t17.v2.stage import StageRawManifest
from skillflow.experiment.t17.v2.stage_contract import unit_identity
from skillflow.experiment.t17.v2.unit_execution import compact_id
from skillflow.experiment.t17.v2.usage_validation import validate_usage
from skillflow.models.base import StrictModel
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document

ModelT = TypeVar("ModelT", bound=StrictModel)


def read_model(path: Path, model: type[ModelT]) -> ModelT:
    """不接受忽略错误或删除错误行的装载方式。"""
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def load_stage(project_root: Path, directory: Path) -> LoadedStage:
    """所有检验均只读，不能补写旧终态或更改失败原因。"""
    root = project_root.resolve()
    relative = directory.resolve().relative_to(root).as_posix()
    output = inside(root, relative)
    manifest = read_model(output / "raw-manifest.json", StageRawManifest)
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    if actual != set(manifest.files) | {"raw-manifest.json"}:
        raise ValueError("v2_raw_file_set_drift")
    verify_files(output, manifest.files)
    config = read_model(output / "configuration.json", V2Configuration)
    matrix = read_model(output / "matrix.json", V2Matrix)
    phase = read_model(output / "phase-contract.json", PhaseContract)
    if (
        manifest.phase_contract_sha256 != model_digest(phase)
        or phase.configuration_sha256 != model_digest(config)
        or phase.matrix_sha256 != model_digest(matrix)
        or matrix != build_matrix(root, config, matrix.stage)
    ):
        raise ValueError("v2_phase_configuration_binding")
    verify_files(root, phase.runtime_files)
    cores: list[CoreTerminal] = []
    replays: list[ReplayTerminal] = []
    for trial in matrix.trials:
        core = read_model(
            output / "terminals" / (compact_id(trial.trial_id) + ".json"), CoreTerminal
        )
        if core.identity != unit_identity(phase, matrix, trial, trial.trial_id):
            raise ValueError("v2_core_scheduled_identity")
        validate_core_binding(config, core)
        if core.data is not None:
            scenario = namespace_grants(
                apply_variant(
                    validate_yaml_document(
                        inside(root, trial.configuration.scenario.root), Scenario
                    ),
                    trial.configuration,
                ),
                core.data.facts.run_id,
            )
            if core.data.analysis_definition != redact_definition(scenario):
                raise ValueError("v2_analysis_definition_drift")
        cores.append(core)
        for alias, identifier in trial.replay_pair_ids.items():
            replay = read_model(
                output / "terminals" / (compact_id(identifier) + ".json"), ReplayTerminal
            )
            if (
                replay.identity != unit_identity(phase, matrix, trial, identifier)
                or replay.target_alias != alias
            ):
                raise ValueError("v2_replay_scheduled_identity")
            validate_replay_binding(core, replay)
            replays.append(replay)
    usage_path = output / "api-usage.jsonl"
    usage = read_journal(usage_path) if usage_path.is_file() else ()
    gate = build_gate(phase, matrix, AnalysisGroup(config, tuple(cores), tuple(replays)), usage)
    if gate != read_model(output / "phase-gate.json", PhaseGate):
        raise ValueError("v2_saved_phase_gate_drift")
    result = StageResult(phase=phase, cores=tuple(cores), replays=tuple(replays), gate=gate)
    validate_usage(result, matrix, usage)
    return LoadedStage(
        configuration=config,
        matrix=matrix,
        result=result,
        raw_relative_path=relative,
        raw_manifest=file_digest(output / "raw-manifest.json"),
        raw_files=manifest.files,
        api_usage=usage,
    )
