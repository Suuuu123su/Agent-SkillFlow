"""T18 可解释的计数、比例和差值；不合成单一安全评分。"""

from typing import Literal, Self

from pydantic import model_validator

from skillflow.models.base import NonEmptyStr, StrictModel


class Measure(StrictModel):
    """所有点估计保留原始分子分母及所属运行证据。"""

    status: Literal["measured", "not_applicable", "not_available", "incomplete"]
    value: float | None
    numerator: float
    denominator: int
    evidence_ids: tuple[NonEmptyStr, ...]
    reason: NonEmptyStr
    interval_status: Literal["not_applicable"] = "not_applicable"
    interval_reason: Literal["single_deterministic_cluster"] = "single_deterministic_cluster"

    @model_validator(mode="after")
    def validate_arithmetic(self) -> Self:
        """不完整数值不得冒充实测零。"""
        if self.denominator < 0:
            raise ValueError("t18_metric_negative_denominator")
        if self.status == "measured":
            if not self.denominator or self.value != self.numerator / self.denominator:
                raise ValueError("t18_metric_arithmetic")
        elif self.value is not None:
            raise ValueError("t18_metric_unmeasured_value")
        return self


def measure(
    numerator: float,
    denominator: int,
    evidence: tuple[str, ...],
    *,
    complete: bool = True,
    reason: str = "scheduled_core",
) -> Measure:
    """零分母仅表示该子群没有适用单位，缺失完成记录优先标记不完整。"""
    return Measure(
        status="incomplete" if not complete else "measured" if denominator else "not_applicable",
        value=numerator / denominator if denominator and complete else None,
        numerator=numerator,
        denominator=denominator,
        evidence_ids=evidence,
        reason=reason,
    )
