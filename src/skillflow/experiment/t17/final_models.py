"""T17 全阶段最终指标索引模型。"""

from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t17.comparison_models import T17CrossModelReport
from skillflow.experiment.t17.defense_models import T17DefenseReport
from skillflow.experiment.t17.metric_models import T17PhaseMetricsReport
from skillflow.models.base import NonEmptyStr, StrictModel

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class T17FinalMetricsReport(StrictModel):
    """A-H 完成后的 Phase、跨模型和 Defense 完整指标。"""

    schema_version: Literal["0.1"] = "0.1"
    report_scope: Literal["t17_final"] = "t17_final"
    report_id: Literal["t17-final-metrics-v1"] = "t17-final-metrics-v1"
    phases: tuple[T17PhaseMetricsReport, ...]
    cross_model: T17CrossModelReport
    defense: T17DefenseReport
    source_sha256: dict[NonEmptyStr, Sha256Hex]
    complete: bool
