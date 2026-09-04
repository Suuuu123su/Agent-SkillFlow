"""第二版完整测量与模型、防御、技能比较报告。"""

from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.v2.run_models import V2Domain
from skillflow.experiment.t17.v2.statistics_models import Measurement
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode

Direction = Literal["negative", "zero", "positive", "indeterminate"]
Agreement = Literal["agreement", "disagreement", "indeterminate"]


class StratumIdentity(StrictModel):
    """明确报告包含哪些调度，不能把相同技能的不同版本自动混合。"""

    protocol_id: NonEmptyStr
    domain: V2Domain
    requested_model: NonEmptyStr
    model_revision: NonEmptyStr
    stages: tuple[T17LiveStage, ...]
    condition_ids: tuple[NonEmptyStr, ...]
    skill_variant_ids: tuple[NonEmptyStr, ...]
    enforcement_modes: tuple[EnforcementMode, ...]
    phase_contract_sha256: tuple[Sha256, ...]
    matrix_sha256: tuple[Sha256, ...]
    skill_content_sha256: dict[NonEmptyStr, Sha256] = Field(default_factory=dict)
    manifest_sha256: dict[NonEmptyStr, Sha256] = Field(default_factory=dict)
    raw_manifest_sha256: tuple[Sha256, ...] = ()


class MetricVectorReport(StrictModel):
    """一个明确分层的全部原始计数、状态、证据和区间。"""

    schema_version: Literal["2.0"] = "2.0"
    report_id: NonEmptyStr
    kind: Literal["stage", "condition", "mode", "skill"]
    identity: StratumIdentity
    scheduled_core: Annotated[int, Field(ge=1)]
    scheduled_replay: Annotated[int, Field(ge=0)]
    metrics: dict[NonEmptyStr, Measurement]
    required_metrics_complete: bool
    primary_population: Literal["scheduled"] = "scheduled"
    independent_review: Literal["REVIEW_UNAVAILABLE"] = "REVIEW_UNAVAILABLE"


class MetricComparison(StrictModel):
    """两侧各保留独立分母；方向一致不等于统计等价。"""

    metric: NonEmptyStr
    left: Measurement
    right: Measurement
    delta: Measurement
    left_point_direction: Direction
    right_point_direction: Direction
    left_interval_direction: Direction
    right_interval_direction: Direction
    point_agreement: Agreement
    interval_agreement: Agreement
    delta_definition: Literal["left_minus_right"] = "left_minus_right"
    interpretation: Literal["descriptive_not_statistical_equivalence"] = (
        "descriptive_not_statistical_equivalence"
    )


class ComparisonReport(StrictModel):
    """比较一个固定因素，不合并两侧生成模型间总体百分比。"""

    schema_version: Literal["2.0"] = "2.0"
    report_id: NonEmptyStr
    kind: Literal["model", "defense", "skill"]
    left: MetricVectorReport
    right: MetricVectorReport
    comparisons: tuple[MetricComparison, ...]
    named_deltas: dict[NonEmptyStr, Measurement] = Field(default_factory=dict)
    complete: bool
