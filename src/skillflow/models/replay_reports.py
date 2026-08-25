"""成对反事实 Replay 的标准结果契约。"""

from typing import Literal, Self

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import Decision
from skillflow.models.references import ScenarioPath


class ConfirmedInfluenceEdge(StrictModel):
    """仅由成对反事实证据确认的 Artifact→Effect 影响边。"""

    source_artifact_id: NonEmptyStr
    target_effect_id: NonEmptyStr
    relation: Literal["INFLUENCE_CONFIRMED"] = "INFLUENCE_CONFIRMED"


class ReplayRiskReport(StrictModel):
    """一次原始/中和 Run 配对的因果影响报告。"""

    schema_version: NonEmptyStr
    report_scope: Literal["replay"]
    replay_id: NonEmptyStr
    experiment_id: NonEmptyStr | None = None
    source_run_id: NonEmptyStr | None = None
    scenario: ScenarioPath | None = None
    target_alias: NonEmptyStr | None = None
    selector_alias: NonEmptyStr | None = None
    original_run_id: NonEmptyStr
    neutral_run_id: NonEmptyStr
    intervention_artifact_id: NonEmptyStr
    original_intervention_artifact_id: NonEmptyStr
    neutral_intervention_artifact_id: NonEmptyStr
    observed_effect_ids: tuple[NonEmptyStr, ...] = ()
    original_effect_ids: tuple[NonEmptyStr, ...] = ()
    neutral_effect_ids: tuple[NonEmptyStr, ...] = ()
    removed_effect_ids: tuple[NonEmptyStr, ...] = ()
    added_effect_ids: tuple[NonEmptyStr, ...] = ()
    original_receipt_ids: tuple[NonEmptyStr, ...] = ()
    neutral_receipt_ids: tuple[NonEmptyStr, ...] = ()
    original_baseline_result: Decision | None = None
    neutral_baseline_result: Decision | None = None
    neutralization_preserves_other_inputs: bool = False
    y_original: bool
    y_neutral: bool
    ci: Literal[-1, 0, 1]
    confirmed_influence_edges: tuple[ConfirmedInfluenceEdge, ...] = ()
    redacted: bool = True

    @model_validator(mode="after")
    def validate_pair_evidence(self) -> Self:
        """拒绝与两分支 Effect 集合不一致的 CI 或确认边。"""
        self._validate_branch_outcomes()
        removed, added = self._validate_effect_diff()
        self._validate_receipts()
        self._validate_edges(removed, added)
        return self

    def _validate_branch_outcomes(self) -> None:
        if self.original_run_id == self.neutral_run_id:
            self._invalid("原始与中和分支必须使用不同 run_id")
        if self.y_original is not bool(self.original_effect_ids):
            self._invalid("y_original 必须等于原始分支是否存在 Effect")
        if self.y_neutral is not bool(self.neutral_effect_ids):
            self._invalid("y_neutral 必须等于中和分支是否存在 Effect")
        if self.ci != int(self.y_original) - int(self.y_neutral):
            self._invalid("CI 必须等于 y_original - y_neutral")

    def _validate_effect_diff(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        observed = tuple(dict.fromkeys((*self.original_effect_ids, *self.neutral_effect_ids)))
        removed = tuple(
            item for item in self.original_effect_ids if item not in self.neutral_effect_ids
        )
        added = tuple(
            item for item in self.neutral_effect_ids if item not in self.original_effect_ids
        )
        if self.observed_effect_ids != observed:
            self._invalid("observed_effect_ids 必须是两分支 Effect 的有序并集")
        if self.removed_effect_ids != removed or self.added_effect_ids != added:
            self._invalid("Effect diff 必须由两分支集合机械计算")
        return removed, added

    def _validate_receipts(self) -> None:
        if self.original_receipt_ids and len(self.original_receipt_ids) != len(
            self.original_effect_ids
        ):
            self._invalid("原始分支的 Effect 与 Receipt 必须逐项对齐")
        if self.neutral_receipt_ids and len(self.neutral_receipt_ids) != len(
            self.neutral_effect_ids
        ):
            self._invalid("中和分支的 Effect 与 Receipt 必须逐项对齐")

    def _validate_edges(
        self,
        removed: tuple[str, ...],
        added: tuple[str, ...],
    ) -> None:
        edge_targets = tuple(edge.target_effect_id for edge in self.confirmed_influence_edges)
        expected_targets = removed if self.ci == 1 else added if self.ci == -1 else ()
        if edge_targets != expected_targets:
            self._invalid("确认影响边必须且只能指向 CI 对应的差异 Effect")
        if any(
            edge.source_artifact_id != self.intervention_artifact_id
            for edge in self.confirmed_influence_edges
        ):
            self._invalid("确认影响边必须从被干预 Artifact 出发")

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("replay_evidence_inconsistent", detail)
