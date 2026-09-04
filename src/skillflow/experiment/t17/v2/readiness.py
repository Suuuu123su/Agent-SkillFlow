"""申请预算前机械复核本轮固定脚本和两种完整模拟，不信任单一通过标记。"""

from pathlib import Path
from typing import TYPE_CHECKING

from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.frozen import FrozenFile, file_digest, inside
from skillflow.experiment.t17.v2.golden_models import GoldenReport, golden_specification
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.loading import load_stage, read_model

if TYPE_CHECKING:
    from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal


def offline_evidence(root: Path, readiness: Path, config_hash: str) -> dict[str, FrozenFile]:
    """证据文件、数量、独立期望、执行域与零 API 必须同时成立。"""
    path = inside(root, readiness.resolve().relative_to(root.resolve()).as_posix())
    golden_path = path / "golden" / "golden-report.json"
    golden = read_model(golden_path, GoldenReport)
    validate_golden(golden, config_hash)
    golden_root = golden_path.parent
    actual = {p.relative_to(golden_root).as_posix() for p in golden_root.rglob("*") if p.is_file()}
    if actual != set(golden.raw_files) | {"golden-report.json"}:
        raise ValueError("v2_golden_file_set_drift")
    for name, digest in golden.raw_files.items():
        if file_digest(inside(golden_root, name)).sha256 != digest:
            raise ValueError("v2_golden_raw_hash_drift")
    evidence = {_relative(root, golden_path): file_digest(golden_path)}
    for name, domain in (
        ("golden/reference", "scripted"),
        ("fake-all", "fake_reference"),
        ("fake-none", "fake_reference"),
    ):
        stage = load_stage(root, path / name)
        _validate_stage(stage, config_hash, domain)
        if (
            name == "golden/reference"
            and model_digest(stage.result.phase) != golden.phase_contract_sha256
        ):
            raise ValueError("v2_golden_phase_binding")
        if name.startswith("fake-"):
            _validate_fake_choice(stage, all_actions=name == "fake-all")
        manifest = path / name / "raw-manifest.json"
        evidence[_relative(root, manifest)] = file_digest(manifest)
    return evidence


def validate_golden(golden: GoldenReport, config_hash: str) -> None:
    """固定任务与风险期望来源独立，不能用运行结果反填期望。"""
    spec = golden_specification()
    if (
        not golden.passed
        or golden.failures
        or golden.configuration_sha256 != config_hash
        or golden.expected_sha256 != model_digest(spec)
        or (golden.core, golden.replay, golden.replicas)
        != (spec.core, spec.replay, spec.core_replicas)
        or set(golden.fingerprints) != set(spec.tasks)
        or golden.tasks != spec.tasks
        or golden.metrics != spec.expected_metrics
        or any(
            len(values) != spec.core_replicas or len(set(values)) != 1
            for values in golden.fingerprints.values()
        )
    ):
        raise ValueError("v2_offline_golden_not_ready")


def _validate_stage(stage: LoadedStage, config_hash: str, domain: str) -> None:
    result = stage.result
    spec = golden_specification()
    if (
        not result.gate.passed
        or model_digest(stage.configuration) != config_hash
        or result.phase.domain != domain
        or (len(result.cores), len(result.replays)) != (spec.core, spec.replay)
    ):
        raise ValueError("v2_offline_stage_not_ready")
    units: tuple[CoreTerminal | ReplayTerminal, ...] = (*result.cores, *result.replays)
    if stage.api_usage or any(u.usage.api_calls for u in units):
        raise ValueError("v2_offline_evidence_is_not_zero_api")


def _validate_fake_choice(stage: LoadedStage, *, all_actions: bool) -> None:
    units: tuple[CoreTerminal | ReplayTerminal, ...] = (*stage.result.cores, *stage.result.replays)
    for unit in units:
        for decision in unit.decisions:
            expected = decision.allowed_action_ids if all_actions else ()
            if decision.selected_action_ids != expected or not decision.schema_valid:
                raise ValueError("v2_fake_choice_drift")


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
