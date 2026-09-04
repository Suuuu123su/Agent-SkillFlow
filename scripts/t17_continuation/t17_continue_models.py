"""用户批准的固定序号续跑；执行条件不变，来源与新增费用分别登记。"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t17.v2.config_models import V2Matrix
from skillflow.experiment.t17.v2.frozen import FrozenFile, file_digest, inside
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal, UnitUsage
from skillflow.experiment.t17.v2.unit_execution import compact_id
from skillflow.models.base import StrictModel


class ContinuationPlan(StrictModel):
    """固定恢复序号、保留来源与原费用边界。"""

    source_raw: str
    output_relative_path: str
    snapshot_relative_path: str
    first_ordinal: Annotated[int, Field(ge=1)]
    first_trial_id: str
    previous_selection: str | None = None
    user_instruction: str = "从第116个开始重跑；之后如果也出错也这样从断点续跑"
    selection_rule: Literal["retain_fixed_prefix_rerun_inclusive_suffix"] = (
        "retain_fixed_prefix_rerun_inclusive_suffix"
    )
    previous_failures_preserved: Literal[True] = True
    automatic_infrastructure_continuation: Literal[True] = True
    max_consecutive_no_progress: Literal[3] = 3
    expense_scope: Literal["new_api_calls_only_previous_costs_already_accounted"] = (
        "new_api_calls_only_previous_costs_already_accounted"
    )


class SourceUnit(StrictModel):
    """一条任务或重放的原始终态位置。"""

    ordinal: int
    kind: Literal["core", "replay"]
    unit_id: str
    source_raw: str
    terminal_file: FrozenFile


class SourceIndex(StrictModel):
    """逐单元登记来源，不把续跑描述成全新独立尝试。"""

    plan: ContinuationPlan
    units: tuple[SourceUnit, ...]
    evidence_kind: Literal["user_authorized_continuation_not_fresh_independent_attempt"] = (
        "user_authorized_continuation_not_fresh_independent_attempt"
    )


class EventLineage(StrictModel):
    """派生账本事件与原账本事件的一对一关联。"""

    sequence: int
    source_raw: str
    source_sequence: int
    source_event_sha256: str


class ContinuationAccounting(StrictModel):
    """选中结果与本次新增调用的用量分别保存。"""

    selected_result_usage: UnitUsage
    new_execution_usage: UnitUsage
    retained_prefix_charged_again: Literal[False] = False
    historical_unknown_usage_preserved: Literal[True] = True


class CompositeRawManifest(StrictModel):
    """仅登记来源索引，不复制私有模型正文。"""

    kind: Literal["continuation_source_index"] = "continuation_source_index"
    source_index: SourceIndex
    files: dict[str, FrozenFile]
    bodies_copied: Literal[False] = False


def terminal_path(root: Path, source: SourceUnit) -> Path:
    """从已登记来源定位项目内的终态文件。"""
    return inside(root, source.source_raw) / "terminals" / (compact_id(source.unit_id) + ".json")


def source_unit(root: Path, raw: Path, ordinal: int, kind: str, unit_id: str) -> SourceUnit:
    """为已存在的终态生成固定序号来源记录。"""
    relative = raw.relative_to(root).as_posix()
    return SourceUnit.model_validate(
        {
            "ordinal": ordinal,
            "kind": kind,
            "unit_id": unit_id,
            "source_raw": relative,
            "terminal_file": file_digest(raw / "terminals" / (compact_id(unit_id) + ".json")),
        }
    )


def retained_sources(
    root: Path, matrix: V2Matrix, plan: ContinuationPlan
) -> tuple[SourceUnit, ...]:
    """只保留固定断点之前的完整前缀，不按模型表现筛样。"""
    if plan.first_ordinal > len(matrix.trials):
        raise ValueError("continuation_start_outside_matrix")
    if matrix.trials[plan.first_ordinal - 1].trial_id != plan.first_trial_id:
        raise ValueError("continuation_anchor_mismatch")
    raw = inside(root, plan.source_raw)
    previous = (
        {s.unit_id: s for s in read_model(inside(root, plan.previous_selection), SourceIndex).units}
        if plan.previous_selection
        else None
    )
    sources: list[SourceUnit] = []
    for ordinal, trial in enumerate(matrix.trials[: plan.first_ordinal - 1], 1):
        for kind, identifier in (
            ("core", trial.trial_id),
            *(("replay", value) for value in trial.replay_pair_ids.values()),
        ):
            source = (
                previous[identifier]
                if previous is not None
                else source_unit(root, raw, ordinal, kind, identifier)
            )
            if source.ordinal != ordinal or source.kind != kind:
                raise ValueError("continuation_prefix_order")
            if file_digest(terminal_path(root, source)) != source.terminal_file:
                raise ValueError("continuation_prefix_changed")
            model = CoreTerminal if kind == "core" else ReplayTerminal
            terminal = read_model(terminal_path(root, source), model)
            if (
                terminal.status not in {"completed", "not_applicable"}
                or not terminal.usage.complete
            ):
                raise ValueError("continuation_prefix_not_complete")
            if terminal.identity.unit_id != identifier:
                raise ValueError("continuation_prefix_identity")
            sources.append(source)
    return tuple(sources)
