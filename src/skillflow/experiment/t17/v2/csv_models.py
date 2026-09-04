"""CSV 使用扁平字段；嵌套证据与区间保持规范 JSON 字符串。"""

from typing import Literal

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.report_models import Agreement, Direction
from skillflow.models.base import StrictModel


class MetricCsvRow(StrictModel):
    """每个指标一行，保留数值、状态、分母、证据与来源合同。"""

    report_id: str
    report_kind: str
    domain: str
    requested_model: str
    model_revision: str
    stages_json: str
    conditions_json: str
    skills_json: str
    defense_modes_json: str
    phase_contracts_json: str
    matrices_json: str
    metric: str
    status: MeasurementStatus
    numerator: float | None
    denominator: float | None
    value: float | None
    scheduled_denominator: int | None
    unit: str
    denominator_scope: str
    complete_clusters: int
    intervals_json: str
    evidence_ids_json: str
    cluster_terms_json: str
    contrast_signs_json: str
    reason: str | None


class ComparisonCsvRow(StrictModel):
    """两侧独立测量及差值，不提供池化总体率。"""

    report_id: str
    comparison_kind: Literal["model", "defense", "skill"]
    metric: str
    left_identity_json: str
    right_identity_json: str
    left_value: float | None
    right_value: float | None
    delta_value: float | None
    delta_status: MeasurementStatus
    left_measurement_json: str
    right_measurement_json: str
    delta_measurement_json: str
    left_point_direction: Direction
    right_point_direction: Direction
    left_interval_direction: Direction
    right_interval_direction: Direction
    point_agreement: Agreement
    interval_agreement: Agreement
    complete_clusters: int
    named_deltas_json: str
