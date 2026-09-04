"""第二版统计合同：重抽样单位为等义表述簇，区间不人为扩宽。"""

import math
from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.minimal.report_models import MinimalMeasurement
from skillflow.models.base import NonEmptyStr, StrictModel

Finite = Annotated[float, Field(allow_inf_nan=False)]
MIN_CLUSTERS: Final = 2
RESAMPLES: Final = 10000
SEED: Final = 17017


class StatisticalInterval(StrictModel):
    """百分位区间只要求下界不大于上界，不强迫包住点估计。"""

    status: MeasurementStatus
    method: Literal["wilson_chain_descriptive", "cluster_bootstrap"]
    confidence: Annotated[float, Field(ge=0.95, le=0.95)] = 0.95
    point: Finite | None = None
    lower: Finite | None = None
    upper: Finite | None = None
    complete_clusters: Annotated[int, Field(ge=0)] = 0
    resamples: Literal[10000] | None = None
    seed: Literal[17017] | None = None
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """非测量状态没有伪造区间，重抽样元数据必须与预注册一致。"""
        if self.status is MeasurementStatus.MEASURED:
            if (
                self.point is None
                or self.lower is None
                or self.upper is None
                or self.lower > self.upper
            ):
                raise ValueError("v2_invalid_interval")
            if self.method == "cluster_bootstrap" and (
                self.complete_clusters < MIN_CLUSTERS
                or self.resamples != RESAMPLES
                or self.seed != SEED
            ):
                raise ValueError("v2_bootstrap_contract")
        elif (
            any(value is not None for value in (self.point, self.lower, self.upper))
            or self.reason is None
        ):
            raise ValueError("v2_nonmeasured_interval_has_value")
        return self


class ClusterTerm(StrictModel):
    """一个统计项在某簇的分子分母，可按簇内重复直接相加。"""

    cluster: NonEmptyStr
    term: NonEmptyStr
    numerator: Finite
    denominator: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Measurement(MinimalMeasurement):
    """沿用四态及分子分母约束，并附该项适用的区间和完整簇数。"""

    schema_version: Literal["2.0"] = "2.0"
    intervals: tuple[StatisticalInterval, ...] = ()
    cluster_terms: tuple[ClusterTerm, ...] = ()
    contrast_signs: dict[NonEmptyStr, Literal[-1, 1]] = Field(default_factory=dict)
    complete_clusters: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validate_finite_intervals(self) -> Self:
        """测量值不接受 NaN；不改变旧指标状态或历史格式。"""
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("v2_nonfinite_metric")
        return self
