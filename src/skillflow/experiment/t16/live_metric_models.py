"""T16-C 可复算的真实模型指标快照。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.preregistration_models import PairRole
from skillflow.models.advanced_metrics import DerivedMetric
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.metrics import MetricStatus, RatioMetric
from skillflow.models.references import EffectSelectorRef

NonNegativeInt = Annotated[int, Field(ge=0)]


class LiveHiaaCellMetric(StrictModel):
    """由 selector 对齐 Tool audit 和 Receipt 计算的一个四格。"""

    cell: HiaaCell
    executed_count: NonNegativeInt
    run_count: NonNegativeInt
    rate: RatioMetric

    @model_validator(mode="after")
    def require_ratio_counts(self) -> Self:
        """原始计数必须与 RatioMetric 一致。"""
        if self.rate.numerator != self.executed_count or self.rate.denominator != self.run_count:
            raise PydanticCustomError("t16c_hiaa_count_mismatch", "HIAA 四格计数不一致")
        return self


class LiveHiaaSummary(StrictModel):
    """同一 harm_selector 的四格发生率和交互效应。"""

    harm_selector: EffectSelectorRef
    p00: LiveHiaaCellMetric
    p01: LiveHiaaCellMetric
    p10: LiveHiaaCellMetric
    p11: LiveHiaaCellMetric
    hiaa_run: DerivedMetric

    @model_validator(mode="after")
    def require_cell_order(self) -> Self:
        """字段必须精确绑定 p00/p01/p10/p11。"""
        if tuple(item.cell for item in (self.p00, self.p01, self.p10, self.p11)) != tuple(HiaaCell):
            raise PydanticCustomError("t16c_hiaa_cell_order", "HIAA 四格顺序错误")
        return self


class LiveOperationalRate(StrictModel):
    """不冒充正式研究指标的 Receipt 操作率。"""

    label: NonEmptyStr
    rate: RatioMetric


class LiveM2SessionRate(StrictModel):
    """M2 role 在指定 Session 的本地 Receipt 发生率。"""

    pair_role: PairRole
    session_index: Literal[1, 3]
    rate: RatioMetric


class UnavailableFormalMetric(StrictModel):
    """缺少必要平台观测时的结构化 N/A。"""

    metric_name: NonEmptyStr
    metric: RatioMetric
    reason: NonEmptyStr

    @model_validator(mode="after")
    def require_not_applicable(self) -> Self:
        """缺失 Hook 不能被伪写成定义值 0。"""
        if self.metric.status is not MetricStatus.NOT_APPLICABLE:
            raise PydanticCustomError("t16c_unavailable_metric_defined", "缺失证据的指标必须为 N/A")
        return self


class LiveUeaSummary(StrictModel):
    """由结构化授权状态、Tool audit 和 Receipt 得到的 UEA 原始计数。"""

    unauthorized_executed_count: NonNegativeInt
    affected_trial_count: NonNegativeInt
    receipt_ids: tuple[NonEmptyStr, ...]


class LiveMetricsReport(StrictModel):
    """T16-C Model1 原始指标报告；外部 Effect 始终为本地模拟。"""

    schema_version: Literal["0.1"] = "0.1"
    simulation_only: Literal[False] = False
    live_model: Literal[True] = True
    external_effects_simulated: Literal[True] = True
    record_count: NonNegativeInt
    hiaa: LiveHiaaSummary
    authorization_operational_rates: tuple[LiveOperationalRate, ...]
    m2_operational_rates: tuple[LiveM2SessionRate, ...]
    uea: LiveUeaSummary
    alr: UnavailableFormalMetric
    rir_1: UnavailableFormalMetric
    rir_3: UnavailableFormalMetric
    provenance_not_available_count: NonNegativeInt

    @model_validator(mode="after")
    def require_direct_harness_provenance_na(self) -> Self:
        """没有 Hook 的直接 Responses Harness 必须逐条记录 provenance N/A。"""
        if self.provenance_not_available_count != self.record_count:
            raise PydanticCustomError("t16c_provenance_na_count", "来源 N/A 数量必须覆盖全部记录")
        return self
