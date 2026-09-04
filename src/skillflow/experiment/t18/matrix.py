"""去重展开 T18 核心任务和完整 HIAA 四格；不采样或执行工具。"""

from typing import Literal, Self

from pydantic import model_validator

from skillflow.models.base import NonEmptyStr, StrictModel

Domain = Literal["scripted", "fake_reference"]
Mode = Literal[
    "monitor",
    "universal_enforce",
    "task_alignment_only",
    "tdg_only",
    "drift_isolation_only",
    "causal_only",
    "all_defenses",
    "oracle_router",
    "evidence_router",
]
ModeCell = Literal["p00", "p01", "p10", "p11"]
Role = Literal["attack", "neutral", "benign-control"]
PAIRED_ROLES: tuple[Role, ...] = ("attack", "neutral")
FACTORS: tuple[tuple[ModeCell, Role, bool], ...] = (
    ("p00", "neutral", False),
    ("p01", "neutral", True),
    ("p10", "attack", False),
    ("p11", "attack", True),
)
MODES: tuple[Mode, ...] = (
    "monitor",
    "universal_enforce",
    "task_alignment_only",
    "tdg_only",
    "drift_isolation_only",
    "causal_only",
    "all_defenses",
    "oracle_router",
    "evidence_router",
)
CONTROL_MODES: tuple[Mode, ...] = ("monitor", "all_defenses", "evidence_router")
FAKE_MODES: tuple[Mode, ...] = ("monitor", "all_defenses", "oracle_router", "evidence_router")
ATTACK_BASES = ("B1", "C1", "C2", "M1", "M2", "A1", "S1", "L1")
HELD_OUT_BASES = ("HP", "HC", "HM", "HA")
BENIGN_BASES = ("B0", "N0", "G0", "A2")


class CoreCell(StrictModel):
    """任务身份独立于结果；桥梁关闭是显式实验因素，不生成隐含子运行。"""

    trial_id: NonEmptyStr
    skill_variant_id: NonEmptyStr
    base_id: NonEmptyStr
    role: Literal["attack", "neutral", "benign-control"]
    split: Literal["development", "held-out", "control"]
    mode: Mode
    bridge_enabled: bool
    semantic_instance: Literal["local-01"] = "local-01"
    repeat: Literal[1] = 1
    seed: NonEmptyStr


class HiaaGroup(StrictModel):
    """同防御、同能力、同任务的四格引用，指标计算无需读取场景标签。"""

    design_id: NonEmptyStr
    base_id: NonEmptyStr
    mode: Mode
    feature: Literal["shared-context", "tool-return-propagation"]
    cells: dict[ModeCell, NonEmptyStr]

    @model_validator(mode="after")
    def validate_cells(self) -> Self:
        """缺格属于不完整设计，不允许降级为不适用。"""
        if set(self.cells) != {"p00", "p01", "p10", "p11"}:
            raise ValueError("t18_hiaa_four_cells_required")
        return self


class LocalMatrix(StrictModel):
    """本次获准规模；阶段执行器不得在此之外自动增加条件。"""

    schema_version: Literal["18.0"] = "18.0"
    protocol_id: Literal["t18-local-hiaa-v1"] = "t18-local-hiaa-v1"
    domain: Domain
    original_core_count: int
    reused_hiaa_cells: int
    added_core_count: int
    max_replay_pairs: int
    cores: tuple[CoreCell, ...]
    hiaa_groups: tuple[HiaaGroup, ...]
    paid_api_calls_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_expansion(self) -> Self:
        """验证数量、身份与四格因素；内容合同在冻结时再由真实目录核对。"""
        by_id = {item.trial_id: item for item in self.cores}
        expected = (228, 36, 36, 20, 18) if self.domain == "scripted" else (32, 4, 12, 8, 4)
        actual = (
            self.original_core_count,
            self.reused_hiaa_cells,
            self.added_core_count,
            self.max_replay_pairs,
            len(self.hiaa_groups),
        )
        if actual != expected or len(by_id) != len(self.cores):
            raise ValueError("t18_matrix_scope_drift")
        if len(self.cores) != self.original_core_count + self.added_core_count:
            raise ValueError("t18_matrix_count_mismatch")
        group_ids: set[str] = set()
        for group in self.hiaa_groups:
            if group.design_id in group_ids or not set(group.cells.values()) <= by_id.keys():
                raise ValueError("t18_hiaa_identity_binding")
            group_ids.add(group.design_id)
            _validate_quartet(group, by_id)
        return self


def _validate_quartet(group: HiaaGroup, by_id: dict[str, CoreCell]) -> None:
    quartet = tuple(by_id[group.cells[name]] for name, _, _ in FACTORS)
    if tuple((c.role, c.bridge_enabled) for c in quartet) != (
        ("neutral", False),
        ("neutral", True),
        ("attack", False),
        ("attack", True),
    ):
        raise ValueError("t18_hiaa_factor_mismatch")
    if any(c.base_id != group.base_id or c.mode != group.mode for c in quartet):
        raise ValueError("t18_hiaa_group_mismatch")
    if len({(c.seed, c.semantic_instance, c.repeat) for c in quartet}) != 1:
        raise ValueError("t18_hiaa_shared_controls_mismatch")


def _cell(
    base: str,
    role: Role,
    mode: Mode,
    enabled: bool = True,
) -> CoreCell:
    identifier = base.lower() + "-" + role
    return CoreCell(
        trial_id=identifier + "." + mode + (".on" if enabled else ".off"),
        skill_variant_id=identifier,
        base_id=base,
        role=role,
        mode=mode,
        bridge_enabled=enabled,
        seed="t18:" + base + ":local-01:repeat-1",
        split="held-out"
        if base in HELD_OUT_BASES
        else ("control" if role == "benign-control" else "development"),
    )


def build_matrix(domain: str) -> LocalMatrix:
    """先生成原计划，再按完整身份复用或添加缺失四格；没有实际模型调用。"""
    if domain not in {"scripted", "fake_reference"}:
        raise ValueError("t18_local_domain_required")
    scripted = domain == "scripted"
    bases = (*ATTACK_BASES, *HELD_OUT_BASES) if scripted else ("B1", "C1", "M2", "A1")
    modes = MODES if scripted else FAKE_MODES
    original = [
        _cell(base, role, mode) for base in bases for role in PAIRED_ROLES for mode in modes
    ]
    if scripted:
        original.extend(
            _cell(base, "benign-control", mode) for base in BENIGN_BASES for mode in CONTROL_MODES
        )
    cells = {item.trial_id: item for item in original}
    groups = []
    reused = 0
    hiaa_modes: tuple[Mode, ...] = MODES if scripted else ("monitor", "evidence_router")
    for base, feature in (("C1", "shared-context"), ("C2", "tool-return-propagation")):
        for mode in hiaa_modes:
            references: dict[str, str] = {}
            for label, role, enabled in FACTORS:
                cell = _cell(base, role, mode, enabled)
                if cell.trial_id in cells:
                    if cells[cell.trial_id] != cell:
                        raise ValueError("t18_reused_cell_contract_mismatch")
                    reused += 1
                else:
                    cells[cell.trial_id] = cell
                references[label] = cell.trial_id
            groups.append(
                HiaaGroup.model_validate(
                    {
                        "design_id": base.lower() + "." + mode,
                        "base_id": base,
                        "mode": mode,
                        "feature": feature,
                        "cells": references,
                    }
                )
            )
    return LocalMatrix(
        domain="scripted" if scripted else "fake_reference",
        original_core_count=len(original),
        reused_hiaa_cells=reused,
        added_core_count=len(cells) - len(original),
        max_replay_pairs=20 if scripted else 8,
        cores=tuple(cells.values()),
        hiaa_groups=tuple(groups),
    )
