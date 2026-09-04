"""注册内容干预和跨会话的成对条件，不按场景标签赋值。"""

from typing import Literal, Self

from pydantic import model_validator

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.scenario_parts import EffectSelector


class SessionPairDesign(StrictModel):
    """两份能力相同的任务在撤销后指定会话比较实际风险操作。"""

    pair_id: NonEmptyStr
    target_skill_variant_id: NonEmptyStr
    control_skill_variant_id: NonEmptyStr
    session_offsets: tuple[Literal[1, 3], ...] = (1, 3)
    selectors: tuple[EffectSelector, ...]

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        """目标与对照必须不同且有明确风险选择器。"""
        if self.target_skill_variant_id == self.control_skill_variant_id or not self.selectors:
            raise ValueError("v2_session_pair_invalid")
        if len(set(self.session_offsets)) != len(self.session_offsets):
            raise ValueError("v2_session_offset_duplicate")
        return self
