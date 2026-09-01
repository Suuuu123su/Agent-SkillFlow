"""T16-C Campaign 重分析报告的不可覆盖创建与恢复校验。"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from skillflow.experiment.t16.live_reanalysis import (
    build_live_reanalysis,
    reanalyze_live_results,
)
from skillflow.experiment.t16.live_reanalysis_models import LiveReanalysisReport
from skillflow.experiment.t16.live_reanalysis_v3 import (
    LiveReanalysisPaths,
    build_live_reanalysis_v3,
    load_live_reanalysis_design,
    reanalyze_live_results_v3,
)
from skillflow.experiment.t16.live_reanalysis_v3_models import LiveReanalysisReportV3
from skillflow.experiment.t16.live_reanalysis_v4 import (
    build_live_reanalysis_v4,
    reanalyze_live_results_v4,
)
from skillflow.experiment.t16.live_reanalysis_v4_models import LiveReanalysisReportV4
from skillflow.experiment.t16.live_store import LiveResultStore


@dataclass(frozen=True, slots=True)
class LiveCampaignReportError(ValueError):
    """恢复时的现存报告无法由当前不可变来源复算。"""

    path: Path
    detail: str

    def __str__(self) -> str:
        """返回不包含模型正文的稳定诊断。"""
        return f"{self.path.name}: {self.detail}"


def load_or_create_live_reanalysis(
    source_path: Path,
    output_path: Path,
    *,
    resume: bool,
) -> LiveReanalysisReport:
    """新运行 exclusive-create；恢复运行只读并与当前来源完整复算对比。"""
    if not output_path.exists() or not resume:
        return reanalyze_live_results(source_path, output_path)
    existing = _read_report(output_path)
    before_hash = _sha256(source_path)
    records = LiveResultStore(source_path).read_records()
    after_hash = _sha256(source_path)
    if before_hash != after_hash:
        raise LiveCampaignReportError(source_path, "读取期间来源记录发生变化")
    expected = build_live_reanalysis(records, source_path.as_posix(), before_hash)
    if existing != expected:
        raise LiveCampaignReportError(output_path, "现存报告与当前来源复算结果不一致")
    return existing


def load_or_create_live_reanalysis_v3(
    paths: LiveReanalysisPaths,
    *,
    resume: bool,
) -> LiveReanalysisReportV3:
    """新建 v0.3，或在恢复时按源证据和两份冻结设计完整复算。"""
    if not paths.output_path.exists() or not resume:
        return reanalyze_live_results_v3(paths)
    existing = _read_report_v3(paths.output_path)
    before_hash = _sha256(paths.source_path)
    records = LiveResultStore(paths.source_path).read_records()
    after_hash = _sha256(paths.source_path)
    if before_hash != after_hash:
        raise LiveCampaignReportError(paths.source_path, "读取期间来源记录发生变化")
    design = load_live_reanalysis_design(
        paths.preregistration_path,
        paths.matrix_path,
    )
    expected = build_live_reanalysis_v3(
        records,
        paths.source_path.as_posix(),
        before_hash,
        design,
    )
    if existing != expected:
        raise LiveCampaignReportError(paths.output_path, "现存 v0.3 报告与当前证据/设计复算不一致")
    return existing


def load_or_create_live_reanalysis_v4(
    paths: LiveReanalysisPaths,
    *,
    resume: bool,
) -> LiveReanalysisReportV4:
    """新建 v0.4，或恢复时按源证据、冻结设计与 Phase Contract 完整复算。"""
    if not paths.output_path.exists() or not resume:
        return reanalyze_live_results_v4(paths)
    existing = _read_report_v4(paths.output_path)
    before_hash = _sha256(paths.source_path)
    records = LiveResultStore(paths.source_path).read_records()
    after_hash = _sha256(paths.source_path)
    if before_hash != after_hash:
        raise LiveCampaignReportError(paths.source_path, "读取期间来源记录发生变化")
    design = load_live_reanalysis_design(
        paths.preregistration_path,
        paths.matrix_path,
    )
    expected = build_live_reanalysis_v4(
        records,
        paths.source_path.as_posix(),
        before_hash,
        design,
    )
    if existing != expected:
        raise LiveCampaignReportError(paths.output_path, "现存 v0.4 报告与当前证据/设计复算不一致")
    return existing


def _read_report(path: Path) -> LiveReanalysisReport:
    try:
        return LiveReanalysisReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise LiveCampaignReportError(path, "现存报告无法严格解析") from error


def _read_report_v3(path: Path) -> LiveReanalysisReportV3:
    try:
        return LiveReanalysisReportV3.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise LiveCampaignReportError(path, "现存 v0.3 报告无法严格解析") from error


def _read_report_v4(path: Path) -> LiveReanalysisReportV4:
    try:
        return LiveReanalysisReportV4.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise LiveCampaignReportError(path, "现存 v0.4 报告无法严格解析") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
    except OSError as error:
        raise LiveCampaignReportError(path, "来源记录无法读取") from error
    return digest.hexdigest()
