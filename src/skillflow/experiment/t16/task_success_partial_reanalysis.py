"""不改写旧 v2 证据的 T16-D.1 部分统计重分析。"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from skillflow.experiment.t16.task_success_partial_data import (
    PairedConditionQuery,
    ResamplingParameters,
    condition_wilson,
    hiaa_analysis,
    paired_clusters,
    read_live_records,
    require_complete_model1,
    session_executed,
    target_executed,
)
from skillflow.experiment.t16.task_success_statistics import (
    bootstrap_paired_difference_interval,
)
from skillflow.experiment.t16.task_success_statistics_models import (
    BootstrapProtocol,
    SourceEvidenceHash,
    T16D1PartialReanalysis,
    UnavailableMetric,
)

EXPECTED_HASHES = {
    "preregistration": "f12f6fe08e0055ebf749f16adc4c104f8cb8271bf3c7cf8202f1c01767a5b907",
    "smoke_matrix": "e876392a07186f0c989ecfc1911a5f03a4fef11f48a8c37a1e5c76e7a1da0731",
    "model1_matrix": "7efbcc31dc0d6792a80894e794b787bccd6f52de82df0c6c7e51fff276adb0b3",
    "model2_subset_matrix": "302e171b4fad25b79cda6f78119d4de23270904536e998e82e6e97e74d5072f6",
    "smoke_results": "89dcbc44ca4084ee41645f189df471353fbbbd99a7365c6346e8d99c058d6738",
    "model1_results": "2538b342bff20799964392eac15f545c47e10f6f55e4c56c315b1a85d3618f04",
    "v04_reanalysis": "325c2ab7231f0773a99f1ac55c8a087e07aa92259b72ed70a0a5e63ae2f24c8a",
}
SOURCE_PATHS = {
    "preregistration": "experiments/t16/preregistration_t16c_v2.yaml",
    "smoke_matrix": "experiments/t16/matrix_smoke_t16c_v2.yaml",
    "model1_matrix": "experiments/t16/matrix_model1_t16c_v2.yaml",
    "model2_subset_matrix": "experiments/t16/matrix_model2_subset_t16c_v2.yaml",
    "smoke_results": "runs/t16c-v2-live-20260829-01/attempt-01/smoke/trial-results.jsonl",
    "model1_results": "runs/t16c-v2-live-20260829-01/attempt-01/model1/trial-results.jsonl",
    "v04_reanalysis": "docs/evidence/t16c-v2-live-reanalysis-v0.4-20260829.json",
}


@dataclass(frozen=True, slots=True)
class PartialReanalysisPaths:
    """所有必须保持字节不变的旧 v2 输入路径。"""

    preregistration: Path
    smoke_matrix: Path
    model1_matrix: Path
    model2_subset_matrix: Path
    smoke_results: Path
    model1_results: Path
    v04_reanalysis: Path


def build_partial_reanalysis(
    paths: PartialReanalysisPaths,
    *,
    bootstrap_resamples: int,
    seed: int,
) -> T16D1PartialReanalysis:
    """严格读取旧记录，仅输出可合法复算的 Effect 聚合。"""
    source_hashes = _verify_source_hashes(paths)
    records = read_live_records(paths.model1_results)
    require_complete_model1(records)
    resampling = ResamplingParameters(resamples=bootstrap_resamples, seed=seed)
    c1_scheduled = hiaa_analysis(
        records,
        valid_only=False,
        resampling=resampling,
    )
    c1_valid = hiaa_analysis(
        records,
        valid_only=True,
        resampling=resampling,
    )
    m2_session_1 = bootstrap_paired_difference_interval(
        paired_clusters(
            records,
            PairedConditionQuery(
                target_condition="m2-target",
                control_condition="m2-control",
                outcome=lambda item: session_executed(item, 1),
            ),
        ),
        bootstrap_resamples,
        seed,
    )
    m2_session_3 = bootstrap_paired_difference_interval(
        paired_clusters(
            records,
            PairedConditionQuery(
                target_condition="m2-target",
                control_condition="m2-control",
                outcome=lambda item: session_executed(item, 3),
            ),
        ),
        bootstrap_resamples,
        seed,
    )
    a1 = bootstrap_paired_difference_interval(
        paired_clusters(
            records,
            PairedConditionQuery(
                target_condition="a1-claim",
                control_condition="a1-neutralized",
                outcome=target_executed,
            ),
        ),
        bootstrap_resamples,
        seed,
    )
    return T16D1PartialReanalysis(
        id="t16c-v2-partial-reanalysis-v0.5-20260829",
        generated_at=datetime(2026, 8, 29, tzinfo=UTC),
        source_hashes=source_hashes,
        record_count=360,
        bootstrap=BootstrapProtocol(
            resamples=bootstrap_resamples,
            seed=seed,
            cluster_unit="semantic_instance_with_all_repeats",
        ),
        c1_scheduled=c1_scheduled,
        c1_valid_sensitivity=c1_valid,
        m2_session_1=m2_session_1,
        m2_session_3=m2_session_3,
        a1_claim_minus_neutralized=a1,
        condition_wilson_intervals=condition_wilson(records),
        task_success=_unavailable("旧 v2 没有平台 Artifact/Receipt 绑定的 TaskSuccessEvidence"),
        uea=_unavailable("本报告不改变正式 UEA 定义；旧 v2 缺少完整授权判定证据"),
        alr=_unavailable("旧 v2 缺少可复核 decision basis 与中和后 baseline 证据"),
        rir=_unavailable("缺少 INFLUENCE_CONFIRMED Hook 或独立 GT_influence"),
        provenance=_unavailable("缺少平台 provenance Hook；模型自报来源不受信任"),
        t16d_evidence_acceptance="BLOCKED",
        warnings=(
            "valid-only 仅为敏感性分析，scheduled HIAA 是主口径。",
            "Wilson CI 为链级描述性区间，不把 repeat 当作独立推断样本。",
            "本报告不得与 v3 bridge/calibration 结果合并。",
        ),
    )


def write_partial_reanalysis(path: Path, report: T16D1PartialReanalysis) -> None:
    """确定性写出新版本报告，不覆盖旧 v0.4。"""
    content = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    path.write_text(f"{content}\n", encoding="utf-8")


def _verify_source_hashes(paths: PartialReanalysisPaths) -> tuple[SourceEvidenceHash, ...]:
    sources = (
        ("preregistration", paths.preregistration),
        ("smoke_matrix", paths.smoke_matrix),
        ("model1_matrix", paths.model1_matrix),
        ("model2_subset_matrix", paths.model2_subset_matrix),
        ("smoke_results", paths.smoke_results),
        ("model1_results", paths.model1_results),
        ("v04_reanalysis", paths.v04_reanalysis),
    )
    output: list[SourceEvidenceHash] = []
    for field, path in sources:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != EXPECTED_HASHES[field]:
            detail = f"旧 v2 证据哈希漂移: {field}"
            raise ValueError(detail)
        output.append(SourceEvidenceHash(path=SOURCE_PATHS[field], sha256=digest))
    return tuple(output)


def _unavailable(reason: str) -> UnavailableMetric:
    return UnavailableMetric(reason=reason)
