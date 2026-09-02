"""T17 跨模型 side-by-side 与方向一致性模型。"""

from enum import StrEnum, unique
from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t17.contracts import (
    EvidenceDomain,
    RatioMeasurement,
)
from skillflow.experiment.t17.metric_models import T17IntervalEstimate
from skillflow.models.base import NonEmptyStr, StrictModel


@unique
class T17Direction(StrEnum):
    """点或区间相对零的封闭方向。"""

    NEGATIVE = "negative"
    ZERO = "zero"
    POSITIVE = "positive"
    INDETERMINATE = "indeterminate"


class T17RatioSideBySide(StrictModel):
    """两个 Evidence Domain 的比例并排展示，禁止 pooled。"""

    metric: NonEmptyStr
    model1: RatioMeasurement
    model2: RatioMeasurement


class T17SignedModelEstimate(StrictModel):
    """一个模型的有符号点估计、区间和两类方向。"""

    model_revision: NonEmptyStr
    interval: T17IntervalEstimate
    point_direction: T17Direction
    interval_direction: T17Direction


class T17DirectionComparison(StrictModel):
    """同一有符号估计量的跨模型方向比较。"""

    metric: NonEmptyStr
    model1: T17SignedModelEstimate
    model2: T17SignedModelEstimate
    point_direction_agreement: bool
    robust_direction_agreement: bool


class T17CrossModelReport(StrictModel):
    """Model1/Model2 独立报告及非 pooled 方向结论。"""

    schema_version: Literal["0.1"] = "0.1"
    report_scope: Literal["t17_cross_model"] = "t17_cross_model"
    report_id: NonEmptyStr
    model1_domain: EvidenceDomain
    model2_domain: EvidenceDomain
    pooled: Literal[False] = False
    source_phase_sha256: dict[NonEmptyStr, Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]]
    side_by_side_ratios: tuple[T17RatioSideBySide, ...]
    signed_directions: tuple[T17DirectionComparison, ...]
    point_direction_agreement: RatioMeasurement
    robust_direction_agreement: RatioMeasurement
    complete: bool
