"""T18 内容包与可信合同分开保存；真值仅供离线评分或 Oracle 基线。"""

from typing import Literal, Self

from pydantic import model_validator

from skillflow.defense.models import Mechanism
from skillflow.defense.task_plan import TrustedTaskPlan
from skillflow.experiment.t17.minimal.contracts import NormalTaskContract
from skillflow.experiment.t17.v2.catalog_models import SkillBundle
from skillflow.experiment.t18.matrix import Role
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.manifest import SkillManifest
from skillflow.models.scenario import Scenario


class LocalSkill(StrictModel):
    """运行输入包含完整可审计声明，不执行外部程序。"""

    skill_variant_id: NonEmptyStr
    base_id: NonEmptyStr
    role: Role
    split: Literal["development", "held-out", "control"]
    scenario_path: NonEmptyStr
    scenario: Scenario
    bundle: SkillBundle
    manifests: dict[NonEmptyStr, SkillManifest]
    task_contract: NormalTaskContract
    task_plan: TrustedTaskPlan
    scoring_labels: tuple[Mechanism, ...]
    paired_skill_id: NonEmptyStr | None
    adaptation_note: NonEmptyStr


class LocalCatalog(StrictModel):
    """完整目录为 28 项；开发检查可以只读前 20 项。"""

    schema_version: Literal["18.0"] = "18.0"
    skills: tuple[LocalSkill, ...]
    held_out_included: bool

    @model_validator(mode="after")
    def validate_registered_pairs(self) -> Self:
        """所有配对均保留相同能力、任务、规则计划和完整授权结构。"""
        by_id = {skill.skill_variant_id: skill for skill in self.skills}
        expected = 28 if self.held_out_included else 20
        if len(by_id) != len(self.skills) or len(by_id) != expected:
            raise ValueError("t18_catalog_identity_or_size")
        for skill in self.skills:
            if skill.paired_skill_id is None:
                continue
            neutral = by_id.get(skill.paired_skill_id)
            if neutral is None or neutral.role != "neutral" or skill.role != "attack":
                raise ValueError("t18_catalog_pair_missing")
            if any(
                getattr(skill, name) != getattr(neutral, name)
                for name in ("base_id", "split", "manifests", "task_contract", "task_plan")
            ):
                raise ValueError("t18_catalog_pair_contract_mismatch")
            left = (
                *skill.scenario.grants,
                *(
                    step.grant
                    for session in skill.scenario.sessions
                    for step in session.steps
                    if step.grant is not None
                ),
            )
            right = (
                *neutral.scenario.grants,
                *(
                    step.grant
                    for session in neutral.scenario.sessions
                    for step in session.steps
                    if step.grant is not None
                ),
            )
            if left != right or skill.bundle.decisions != neutral.bundle.decisions:
                raise ValueError("t18_catalog_pair_grant_drift")
            if {k: v.output_mime_type for k, v in skill.bundle.scripts.items()} != {
                k: v.output_mime_type for k, v in neutral.bundle.scripts.items()
            }:
                raise ValueError("t18_catalog_pair_output_contract_drift")
        return self
