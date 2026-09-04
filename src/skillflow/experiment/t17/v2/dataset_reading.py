"""只用标准数据集重算全部报告，不读取私有请求、响应或本地数据库。"""

from collections.abc import Iterable, Iterator
from itertools import zip_longest
from pathlib import Path
from typing import TypeVar

from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.catalog_models import SkillCatalog
from skillflow.experiment.t17.v2.csv_export import comparison_rows, metric_rows
from skillflow.experiment.t17.v2.dataset_analysis import dataset_reports
from skillflow.experiment.t17.v2.dataset_integrity import verify_dataset_files
from skillflow.experiment.t17.v2.dataset_models import DatasetManifest, DatasetReports, DatasetStage
from skillflow.experiment.t17.v2.dataset_projection import (
    effect_rows,
    provenance_rows,
    task_rows,
    usage_rows,
)
from skillflow.experiment.t17.v2.dataset_reports_io import read_reports
from skillflow.experiment.t17.v2.dataset_rows import (
    ApiUsageRow,
    CoreRow,
    EffectReceiptRow,
    ProvenanceRow,
    ReplayRow,
    TaskEvidenceRow,
)
from skillflow.experiment.t17.v2.dataset_tables import jsonl_table_rows, validate_csv_rows
from skillflow.experiment.t17.v2.journal import verify_journal
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.phase_validation import validate_structured_stage
from skillflow.experiment.t17.v2.run_models import CoreTerminal, StageResult
from skillflow.models.base import StrictModel

ModelT = TypeVar("ModelT", bound=StrictModel)


def jsonl_rows(path: Path, model: type[ModelT]) -> Iterator[ModelT]:
    """逐行类型校验，空行或损坏行不能忽略。"""
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield model.model_validate_json(line)


def load_dataset(directory: Path) -> tuple[LoadedStage, ...]:
    """核对所有公开事实、派生表和完整指标，不依赖汇总百分比反推。"""
    manifest = verify_dataset_files(directory)
    tables = manifest.tables
    cores = tuple(
        row.restore() for row in jsonl_table_rows(directory, tables["core-trials.jsonl"], CoreRow)
    )
    replay_rows = tuple(jsonl_table_rows(directory, tables["replay-pairs.jsonl"], ReplayRow))
    api_rows = tuple(jsonl_table_rows(directory, tables["api-usage.jsonl"], ApiUsageRow))
    stages = tuple(_restore_stage(s, cores, replay_rows, api_rows) for s in manifest.stages)
    _validate_manifest(manifest, stages, len(cores), len(replay_rows))
    if (
        read_model(directory / "skill-catalog.json", SkillCatalog)
        != stages[0].configuration.catalog
    ):
        raise ValueError("v2_dataset_catalog_binding")
    for stage in stages:
        validate_structured_stage(stage)
    _same_rows(directory, tables["task-success-evidence.jsonl"], TaskEvidenceRow, task_rows(stages))
    _same_rows(directory, tables["effect-receipts.jsonl"], EffectReceiptRow, effect_rows(stages))
    _same_rows(directory, tables["provenance-edges.jsonl"], ProvenanceRow, provenance_rows(stages))
    _same_rows(directory, tables["api-usage.jsonl"], ApiUsageRow, usage_rows(stages))
    reports = dataset_reports(stages)
    if reports != read_reports(directory, "reports.json"):
        raise ValueError("v2_dataset_recomputed_metrics_drift")
    _validate_csv(directory, manifest, reports)
    if manifest.all_provided_stages_passed != (
        all(s.result.gate.passed for s in stages)
        and all(v.required_metrics_complete for v in reports.vectors)
    ):
        raise ValueError("v2_dataset_completion_claim_drift")
    return stages


def _restore_stage(
    source: DatasetStage,
    cores: tuple[CoreTerminal, ...],
    replays: tuple[ReplayRow, ...],
    api: tuple[ApiUsageRow, ...],
) -> LoadedStage:
    phase_hashes = {model_digest(p) for p in (source.phase, *source.source_phases)}
    selected = tuple(c for c in cores if c.identity.phase_contract_sha256 in phase_hashes)
    by_trial = {c.identity.trial_id: c for c in selected}
    if any(
        r.identity.trial_id not in by_trial
        for r in replays
        if r.identity.phase_contract_sha256 in phase_hashes
    ):
        raise ValueError("v2_dataset_replay_without_core")
    selected_replay = tuple(
        r.restore(by_trial[r.identity.trial_id])
        for r in replays
        if r.identity.phase_contract_sha256 in phase_hashes
    )
    usage = tuple(r.event for r in api if r.identity.phase_contract_sha256 in phase_hashes)
    verify_journal(usage, allowed_phases=frozenset(phase_hashes))
    return LoadedStage(
        configuration=source.configuration,
        matrix=source.matrix,
        result=StageResult(
            phase=source.phase,
            cores=selected,
            replays=selected_replay,
            gate=source.gate,
            source_phases=source.source_phases,
        ),
        raw_relative_path=source.raw_relative_path,
        raw_manifest=source.raw_manifest,
        raw_files=source.raw_files,
        api_usage=usage,
    )


def _validate_manifest(
    manifest: DatasetManifest, stages: tuple[LoadedStage, ...], core_count: int, replay_count: int
) -> None:
    if not stages or len({model_digest(s.result.phase) for s in stages}) != len(stages):
        raise ValueError("v2_dataset_stage_identity_duplicate")
    if any(
        s.configuration != stages[0].configuration
        or s.result.phase.protocol_id != manifest.protocol_id
        for s in stages
    ):
        raise ValueError("v2_dataset_protocol_configuration_drift")
    if (
        manifest.scheduled_core != core_count
        or manifest.scheduled_replay != replay_count
        or sum(len(s.result.cores) for s in stages) != core_count
        or sum(len(s.result.replays) for s in stages) != replay_count
    ):
        raise ValueError("v2_dataset_unassigned_or_missing_units")
    if manifest.contains_live_data != any(
        s.result.phase.domain == "live_reference" for s in stages
    ):
        raise ValueError("v2_dataset_evidence_domain_claim_drift")


def _same_rows(
    directory: Path, parts: tuple[str, ...], model: type[ModelT], expected: Iterable[ModelT]
) -> None:
    for actual, calculated in zip_longest(jsonl_table_rows(directory, parts, model), expected):
        if actual != calculated:
            raise ValueError("v2_dataset_projection_table_drift")


def _validate_csv(directory: Path, manifest: DatasetManifest, reports: DatasetReports) -> None:
    for filename, kind in (
        ("metrics-long.csv", None),
        ("condition-summary.csv", "condition"),
        ("skill-comparison-ready.csv", "skill"),
    ):
        validate_csv_rows(directory, manifest.tables[filename], metric_rows(reports, kind))
    for kind in ("model", "defense", "skill"):
        validate_csv_rows(
            directory, manifest.tables[kind + "-comparison.csv"], comparison_rows(reports, kind)
        )
