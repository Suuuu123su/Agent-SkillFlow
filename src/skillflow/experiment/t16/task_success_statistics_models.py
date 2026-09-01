"""T16-C v2 partial reanalysis v0.5 的严格报告模型。"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from skillflow.experiment.t16.task_success_evidence import Sha256Hex
from skillflow.experiment.t16.task_success_statistics import (
    BootstrapEstimate,
    ConfidenceInterval,
)
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell

NonNegativeInt = Annotated[int, Field(ge=0)]


class SourceEvidenceHash(StrictModel):
    """一个旧 v2 输入文件的固定 SHA-256。"""

    path: NonEmptyStr
    sha256: Sha256Hex


class BootstrapProtocol(StrictModel):
    """聚类 Bootstrap 的固定随机协议。"""

    confidence_level: Annotated[float, Field(ge=0.95, le=0.95)] = 0.95
    resamples: Annotated[int, Field(ge=10_000)]
    seed: int
    cluster_unit: Literal["semantic_instance_with_all_repeats"]
    repeat_independence_assumed: Literal[False] = False


class CountRate(StrictModel):
    """分子、分母与点估计。"""

    successes: NonNegativeInt
    total: NonNegativeInt
    value: float


class HiaaCellEstimate(StrictModel):
    """一个 C1 四格的执行率。"""

    cell: HiaaCell
    execution: CountRate


class HiaaAnalysis(StrictModel):
    """scheduled 或 valid-only 的 HIAA 分析。"""

    denominator_policy: Literal["scheduled", "valid_only_sensitivity"]
    cells: Annotated[tuple[HiaaCellEstimate, ...], Field(min_length=4, max_length=4)]
    hiaa: BootstrapEstimate


class ConditionWilsonEstimate(StrictModel):
    """单条件 target Effect 率的描述性 Wilson 区间。"""

    condition_id: NonEmptyStr
    successes: NonNegativeInt
    total: NonNegativeInt
    value: float
    interval: ConfidenceInterval
    inference_note: Literal["descriptive_chain_level_not_cluster_adjusted"]


class UnavailableMetric(StrictModel):
    """旧 v2 无法合法恢复的结构化 N/A。"""

    status: Literal["not_available"] = "not_available"
    value: None = None
    reason: NonEmptyStr


class T16D1PartialReanalysis(StrictModel):
    """只包含旧 v2 可合法计算的聚合统计。"""

    schema_version: Literal["0.5-partial"] = "0.5-partial"
    id: NonEmptyStr
    generated_at: AwareDatetime
    source_hashes: Annotated[tuple[SourceEvidenceHash, ...], Field(min_length=7)]
    record_count: Literal[360]
    old_v2_records_modified: Literal[False] = False
    bootstrap: BootstrapProtocol
    c1_scheduled: HiaaAnalysis
    c1_valid_sensitivity: HiaaAnalysis
    m2_session_1: BootstrapEstimate
    m2_session_3: BootstrapEstimate
    a1_claim_minus_neutralized: BootstrapEstimate
    condition_wilson_intervals: Annotated[
        tuple[ConditionWilsonEstimate, ...],
        Field(min_length=12, max_length=12),
    ]
    task_success: UnavailableMetric
    uea: UnavailableMetric
    alr: UnavailableMetric
    rir: UnavailableMetric
    provenance: UnavailableMetric
    t16d_evidence_acceptance: Literal["BLOCKED"]
    warnings: tuple[NonEmptyStr, ...]
