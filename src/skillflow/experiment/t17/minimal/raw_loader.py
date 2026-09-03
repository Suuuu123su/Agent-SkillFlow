"""最小域的强绑定 Raw 读取器；不同执行域从不混合。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.inputs import apply_variant, namespace_grants
from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.minimal.artifacts import (
    file_digest,
    model_digest,
    resolve_relative,
    verify_raw_manifest,
    verify_runtime_source,
    yaml_digest,
)
from skillflow.experiment.t17.minimal.contracts import MinimalConfiguration
from skillflow.experiment.t17.minimal.raw_core import verify_core_record
from skillflow.experiment.t17.minimal.raw_replay import verify_replay
from skillflow.experiment.t17.minimal.raw_validation import read_model
from skillflow.experiment.t17.minimal.run_models import (
    MinimalExecutionStatus,
    MinimalPhaseContract,
    MinimalRunRecord,
    RawManifest,
)
from skillflow.models.reports import ReplayRiskReport, RunRiskReport
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class MinimalDomainData:
    """已经过 Raw 校验的不可变分析输入。"""

    configuration: MinimalConfiguration
    phase: MinimalPhaseContract
    manifest: RawManifest
    records: tuple[MinimalRunRecord, ...]
    runs: tuple[RunRiskReport, ...]
    replays: tuple[ReplayRiskReport, ...]


def load_minimal_domain(root: Path, project_root: Path = Path()) -> MinimalDomainData:
    """所有调度、ID、Raw 内容和重算结果一致才交给指标层。"""
    phase = read_model(root / "phase-contract.json", MinimalPhaseContract)
    configuration = read_model(root / "configuration.json", MinimalConfiguration)
    manifest = read_model(root / "raw-manifest.json", RawManifest)
    status = read_model(root / "execution-status.json", MinimalExecutionStatus)
    if (
        status.status is not MeasurementStatus.MEASURED
        or status.domain != phase.domain
        or status.phase_contract_sha256 != model_digest(phase)
    ):
        raise ValueError("minimal_execution_status_incomplete_or_unbound")
    if manifest.domain != phase.domain or manifest.phase_contract_sha256 != model_digest(phase):
        raise ValueError("minimal_manifest_phase_domain_mismatch")
    if (
        yaml_digest(configuration) != phase.configuration_sha256
        or yaml_digest(configuration.matrix) != phase.matrix_sha256
    ):
        raise ValueError("minimal_phase_configuration_binding")
    verify_raw_manifest(root, manifest)
    verify_runtime_source(phase, project_root)
    for reference, expected_hash in configuration.source_sha256.items():
        if file_digest(resolve_relative(project_root, reference)) != expected_hash:
            raise ValueError("minimal_source_hash_drift")
    records = _records(root, configuration, phase)
    runs = tuple(verify_core_record(root, item, configuration, project_root) for item in records)
    replays = _replays(root, phase)
    _verify_pairs(root, project_root, configuration, records, replays)
    # 只读重建后再次核对，确保校验没有改写任何 Raw 字节。
    verify_raw_manifest(root, manifest)
    return MinimalDomainData(configuration, phase, manifest, records, runs, replays)


def _records(
    root: Path,
    configuration: MinimalConfiguration,
    phase: MinimalPhaseContract,
) -> tuple[MinimalRunRecord, ...]:
    records = tuple(
        read_model(path, MinimalRunRecord)
        for path in sorted((root / "runs").glob("*/minimal-run-record.json"))
    )
    by_variant = {item.variant: item for item in records}
    expected_variants = {item.variant for item in configuration.matrix.variants}
    if len(records) != phase.expected_core_runs or set(by_variant) != expected_variants:
        raise ValueError("minimal_core_schedule_incomplete")
    if len({item.run_id for item in records}) != len(records):
        raise ValueError("minimal_duplicate_core_run")
    if any(
        item.domain != phase.domain or item.phase_contract_sha256 != model_digest(phase)
        for item in records
    ):
        raise ValueError("minimal_cross_domain_or_phase_record")
    return records


def _replays(root: Path, phase: MinimalPhaseContract) -> tuple[ReplayRiskReport, ...]:
    replays = tuple(
        read_model(path, ReplayRiskReport)
        for path in sorted((root / "replays").glob("*/replay-report.json"))
    )
    if len(replays) != phase.expected_replay_pairs or len(
        {item.replay_id for item in replays}
    ) != len(replays):
        raise ValueError("minimal_replay_schedule_incomplete")
    return replays


def _verify_pairs(
    root: Path,
    project_root: Path,
    configuration: MinimalConfiguration,
    records: tuple[MinimalRunRecord, ...],
    replays: tuple[ReplayRiskReport, ...],
) -> None:
    by_variant = {item.variant: item for item in records}
    expected: set[tuple[str, str, str]] = set()
    for variant in configuration.matrix.variants:
        if variant.variant not in configuration.replay_variants:
            continue
        run_id = by_variant[variant.variant].run_id
        scenario = namespace_grants(
            apply_variant(
                validate_yaml_document(project_root / variant.scenario.root, Scenario),
                variant,
            ),
            run_id,
        )
        for counterfactual in scenario.counterfactuals:
            expected.add((run_id, counterfactual.target.alias, counterfactual.observe.alias))
        for report in replays:
            if report.source_run_id == run_id:
                if report.scenario != variant.scenario:
                    raise ValueError("minimal_replay_scenario_binding")
                verify_replay(root, report, variant, scenario)
    actual = {(item.source_run_id, item.target_alias, item.selector_alias) for item in replays}
    if actual != expected:
        raise ValueError("minimal_replay_pair_binding")
