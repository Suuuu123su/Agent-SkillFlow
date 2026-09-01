"""T16-C 0.3：绑定实际冻结设计并从原始 audit 离线重分析。"""

import hashlib
import json
import os
from argparse import ArgumentParser
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from skillflow.analysis.metric_helpers import ratio_metric
from skillflow.experiment.t16.live_metric_models import UnavailableFormalMetric
from skillflow.experiment.t16.live_reanalysis_models import LegacyOutcomeSummary
from skillflow.experiment.t16.live_reanalysis_v3_metrics import build_audit_metric_bundle
from skillflow.experiment.t16.live_reanalysis_v3_models import (
    LiveDesignBinding,
    LiveReanalysisReportV3,
)
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.live_store import LiveResultStore
from skillflow.experiment.t16.matrix import (
    MatrixKind,
    T16Matrix,
    load_matrix,
    validate_matrix_against_preregistration,
)
from skillflow.experiment.t16.preregistration import load_preregistration
from skillflow.experiment.t16.preregistration_models import T16Preregistration
from skillflow.experiment.t16.trial import ProvenanceStatus, TrialOutcome

SOURCE_CHANGED_ERROR = "读取期间 trial-results.jsonl 发生变化，拒绝重分析"
DESIGN_CHANGED_ERROR = "读取期间冻结设计文件发生变化，拒绝重分析"
DESIGN_VERSION_ERROR = "v0.3 报告要求预注册与 Matrix 使用相同的 0.1 或 0.2 Schema"
MATRIX_KIND_ERROR = "v0.3 完整报告只接受 model1 Matrix"
DUPLICATE_TRIAL_ERROR = "来源记录包含重复 trial_id"
INCOMPLETE_TRIAL_SET_ERROR = "来源记录与冻结 Matrix 的 Trial 完整集合不一致"
MATRIX_TRIAL_SET_ERROR = "record.matrix_trial_id 与冻结 Matrix 完整集合不一致"
TRIAL_ID_MAPPING_ERROR = "result.trial_id 与 matrix_trial_id 的稳定映射不一致"


@dataclass(frozen=True, slots=True)
class LiveReanalysisV3Error(ValueError):
    """来源或冻结设计无法满足 v0.3 重分析合同。"""

    detail: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return self.detail


@dataclass(frozen=True, slots=True)
class LiveReanalysisV3WriteError(OSError):
    """v0.3 报告无法以不可覆盖方式写出。"""

    path: Path
    detail: str

    def __str__(self) -> str:
        """返回稳定文件诊断。"""
        return f"{self.path.name}: {self.detail}"


@dataclass(frozen=True, slots=True)
class LiveReanalysisPaths:
    """一次 v0.3 离线重分析的四个显式文件边界。"""

    source_path: Path
    output_path: Path
    preregistration_path: Path
    matrix_path: Path


@dataclass(frozen=True, slots=True)
class LoadedLiveReanalysisDesign:
    """已经过机械展开复核且在读取期间未漂移的实际冻结设计。"""

    preregistration_path: Path
    matrix_path: Path
    preregistration_sha256: str
    matrix_sha256: str
    registration: T16Preregistration
    matrix: T16Matrix
    expected_trial_ids: tuple[str, ...]


def load_live_reanalysis_design(
    preregistration_path: Path,
    matrix_path: Path,
) -> LoadedLiveReanalysisDesign:
    """加载实际预注册和完整单模型 Matrix，并拒绝读取期漂移。"""
    preregistration_before = _sha256(preregistration_path)
    matrix_before = _sha256(matrix_path)
    registration = load_preregistration(preregistration_path)
    matrix = load_matrix(matrix_path)
    preregistration_after = _sha256(preregistration_path)
    matrix_after = _sha256(matrix_path)
    if preregistration_before != preregistration_after or matrix_before != matrix_after:
        raise LiveReanalysisV3Error(DESIGN_CHANGED_ERROR)
    if (
        registration.schema_version not in {"0.1", "0.2"}
        or matrix.schema_version != registration.schema_version
    ):
        raise LiveReanalysisV3Error(DESIGN_VERSION_ERROR)
    if matrix.kind is not MatrixKind.MODEL1:
        raise LiveReanalysisV3Error(MATRIX_KIND_ERROR)
    validate_matrix_against_preregistration(matrix, registration)
    expected = tuple(sorted(f"live--{item.trial_id}" for item in matrix.trials))
    return LoadedLiveReanalysisDesign(
        preregistration_path=preregistration_path,
        matrix_path=matrix_path,
        preregistration_sha256=preregistration_before,
        matrix_sha256=matrix_before,
        registration=registration,
        matrix=matrix,
        expected_trial_ids=expected,
    )


def build_live_reanalysis_v3(
    records: tuple[LiveTrialRecord, ...],
    source_trial_results_path: str,
    source_trial_results_sha256: str,
    design: LoadedLiveReanalysisDesign,
) -> LiveReanalysisReportV3:
    """绑定完整 Matrix 后，构造不信任 TrialResult 执行布尔值的报告。"""
    ordered = tuple(sorted(records, key=lambda item: item.result.trial_id))
    _require_complete_design_records(ordered, design)
    metrics = build_audit_metric_bundle(ordered)
    binding = _design_binding(ordered, design)
    return LiveReanalysisReportV3(
        source_trial_results_path=source_trial_results_path,
        source_trial_results_sha256=source_trial_results_sha256,
        source_record_count=len(ordered),
        design_binding=binding,
        evidence_basis=metrics.evidence_basis,
        legacy_outcomes=_legacy_outcomes(ordered),
        hiaa=metrics.hiaa,
        authorization_operational_rates=metrics.authorization_operational_rates,
        m2_operational_rates=metrics.m2_operational_rates,
        target_execution_authorization=metrics.target_execution_authorization,
        operational_design_labeled_uea=metrics.operational_design_labeled_uea,
        formal_uea=_unavailable(
            "UEA",
            "直接 Prompt Contract 未观测真实 AuthorizationGrant；预注册授权标签不能替代 Grant",
        ),
        alr=_unavailable(
            "ALR",
            "未观测真实 Grant、完整 decision_basis 与可复验 baseline reason",
        ),
        rir_1=_unavailable(
            "RIR_1",
            "没有平台 INFLUENCE_CONFIRMED Hook 或独立 GT_influence",
        ),
        rir_3=_unavailable(
            "RIR_3",
            "没有平台 INFLUENCE_CONFIRMED Hook 或独立 GT_influence",
        ),
        provenance=_unavailable(
            "provenance",
            "没有平台 provenance Hook 或外部 Oracle；模型自报 origin_ids 不受信任",
        ),
        provenance_not_available_count=sum(
            item.result.provenance.status is ProvenanceStatus.NOT_AVAILABLE for item in ordered
        ),
    )


def reanalyze_live_results_v3(paths: LiveReanalysisPaths) -> LiveReanalysisReportV3:
    """复验源与设计字节，完整集合匹配后 exclusive-create v0.3 报告。"""
    source_before = _sha256(paths.source_path)
    records = LiveResultStore(paths.source_path).read_records()
    source_after = _sha256(paths.source_path)
    if source_before != source_after:
        raise LiveReanalysisV3Error(SOURCE_CHANGED_ERROR)
    design = load_live_reanalysis_design(
        paths.preregistration_path,
        paths.matrix_path,
    )
    report = build_live_reanalysis_v3(
        records,
        paths.source_path.as_posix(),
        source_before,
        design,
    )
    _write_exclusive(paths.output_path, report)
    return report


def _require_complete_design_records(
    records: tuple[LiveTrialRecord, ...],
    design: LoadedLiveReanalysisDesign,
) -> None:
    observed = tuple(item.result.trial_id for item in records)
    if len(set(observed)) != len(observed):
        raise LiveReanalysisV3Error(DUPLICATE_TRIAL_ERROR)
    if observed != design.expected_trial_ids:
        raise LiveReanalysisV3Error(INCOMPLETE_TRIAL_SET_ERROR)
    expected_matrix_ids = {item.trial_id for item in design.matrix.trials}
    observed_matrix_ids = {item.matrix_trial_id for item in records}
    if observed_matrix_ids != expected_matrix_ids:
        raise LiveReanalysisV3Error(MATRIX_TRIAL_SET_ERROR)
    mismatched = tuple(
        item.result.trial_id
        for item in records
        if item.result.trial_id != f"live--{item.matrix_trial_id}"
    )
    if mismatched:
        raise LiveReanalysisV3Error(TRIAL_ID_MAPPING_ERROR)


def _design_binding(
    records: tuple[LiveTrialRecord, ...],
    design: LoadedLiveReanalysisDesign,
) -> LiveDesignBinding:
    observed = tuple(item.result.trial_id for item in records)
    return LiveDesignBinding(
        preregistration_path=design.preregistration_path.as_posix(),
        preregistration_sha256=design.preregistration_sha256,
        preregistration_id=design.registration.id,
        preregistration_schema_version=design.registration.schema_version,
        matrix_path=design.matrix_path.as_posix(),
        matrix_sha256=design.matrix_sha256,
        matrix_id=design.matrix.id,
        matrix_schema_version=design.matrix.schema_version,
        expected_trial_count=len(design.expected_trial_ids),
        expected_trial_ids=design.expected_trial_ids,
        observed_trial_ids=observed,
        model_input_manifest_sha256=_model_input_manifest_sha256(records),
        unique_model_input_count=len({item.model_input_sha256 for item in records}),
    )


def _model_input_manifest_sha256(records: tuple[LiveTrialRecord, ...]) -> str:
    manifest = "".join(
        f"{item.result.trial_id}\t{item.model_input_sha256}\n"
        for item in sorted(records, key=lambda record: record.result.trial_id)
    )
    return hashlib.sha256(manifest.encode()).hexdigest()


def _legacy_outcomes(records: tuple[LiveTrialRecord, ...]) -> LegacyOutcomeSummary:
    return LegacyOutcomeSummary(
        harm_count=sum(item.result.outcome is TrialOutcome.HARM for item in records),
        completed_without_harm_count=sum(
            item.result.outcome is TrialOutcome.COMPLETED_WITHOUT_HARM for item in records
        ),
        invalid_count=sum(item.result.outcome is TrialOutcome.INVALID for item in records),
        refusal_count=sum(item.result.refusal for item in records),
    )


def _unavailable(name: str, reason: str) -> UnavailableFormalMetric:
    return UnavailableFormalMetric(
        metric_name=name,
        metric=ratio_metric(0, 0, ()),
        reason=reason,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
    except OSError as error:
        detail = f"{path.name}: {error}"
        raise LiveReanalysisV3Error(detail) from error
    return digest.hexdigest()


def _write_exclusive(path: Path, report: LiveReanalysisReportV3) -> None:
    content = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{content}\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise LiveReanalysisV3WriteError(path, str(error)) from error


def main(argv: Sequence[str] | None = None) -> int:
    """运行无网络且显式绑定 preregistration/Matrix 的 v0.3 CLI。"""
    parser = ArgumentParser(description="T16-C 0.3 设计绑定离线重分析")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    arguments = parser.parse_args(argv)
    reanalyze_live_results_v3(
        LiveReanalysisPaths(
            source_path=arguments.source,
            output_path=arguments.output,
            preregistration_path=arguments.preregistration,
            matrix_path=arguments.matrix,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
