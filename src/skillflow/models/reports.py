"""按 report_scope 判别并向后兼容导出的风险报告契约。"""

from typing import Annotated

from pydantic import Field, TypeAdapter

from skillflow.models.experiment_reports import (
    ExperimentRiskReport,
    HiaaDesignResult,
    RawCounts,
)
from skillflow.models.replay_reports import ConfirmedInfluenceEdge, ReplayRiskReport
from skillflow.models.run_reports import RunRiskReport

RiskReport = Annotated[
    RunRiskReport | ReplayRiskReport | ExperimentRiskReport,
    Field(discriminator="report_scope"),
]
RISK_REPORT_ADAPTER: TypeAdapter[RiskReport] = TypeAdapter(RiskReport)

__all__ = [
    "RISK_REPORT_ADAPTER",
    "ConfirmedInfluenceEdge",
    "ExperimentRiskReport",
    "HiaaDesignResult",
    "RawCounts",
    "ReplayRiskReport",
    "RiskReport",
    "RunRiskReport",
]
