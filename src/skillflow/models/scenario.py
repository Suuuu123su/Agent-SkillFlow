"""Scenario DSL 顶层模型与引用完整性检查。"""

from typing import Annotated, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.scenario_parts import (
    AssetSpec,
    ClockSpec,
    CounterfactualSpec,
    EffectSelector,
    ExecutionConfig,
    HarnessConfig,
    OracleSpec,
    ScenarioSkill,
    SessionSpec,
    TaskSpec,
)


def _duplicates(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return tuple(sorted(repeated))


class Scenario(StrictModel):
    """可静态验证、不可执行任意代码的完整实验场景。"""

    schema_version: NonEmptyStr
    id: NonEmptyStr
    description: NonEmptyStr
    clock: ClockSpec
    task: TaskSpec
    assets: tuple[AssetSpec, ...] = ()
    skills: Annotated[tuple[ScenarioSkill, ...], Field(min_length=1)]
    harness: HarnessConfig
    execution: ExecutionConfig
    grants: tuple[AuthorizationGrant, ...] = ()
    effect_selectors: tuple[EffectSelector, ...] = ()
    sessions: Annotated[tuple[SessionSpec, ...], Field(min_length=1)]
    oracle: OracleSpec
    counterfactuals: tuple[CounterfactualSpec, ...] = ()

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        """校验声明 ID 与输出别名各自在全局唯一。"""
        asset_ids = tuple(asset.id for asset in self.assets)
        skill_ids = tuple(skill.id for skill in self.skills)
        selector_ids = tuple(selector.alias for selector in self.effect_selectors)
        session_ids = tuple(session.id for session in self.sessions)
        step_ids = tuple(step.id for session in self.sessions for step in session.steps)
        artifact_ids = tuple(
            output.alias
            for session in self.sessions
            for step in session.steps
            for output in step.outputs
        )
        self._reject_duplicates(
            ("asset", asset_ids),
            ("skill", skill_ids),
            ("effect selector", selector_ids),
            ("session", session_ids),
            ("step", step_ids),
            ("artifact alias", artifact_ids),
        )
        return self

    @model_validator(mode="after")
    def validate_skill_and_grant_references(self) -> Self:
        """校验步骤 Skill 与 Grant 的任务和受权主体引用。"""
        declared_skills = frozenset(skill.id for skill in self.skills)
        for session in self.sessions:
            for step in session.steps:
                if step.skill is not None and step.skill not in declared_skills:
                    self._undeclared("skill", step.skill)

        for grant in self.grants:
            if grant.grantee_id not in declared_skills:
                self._undeclared("grant grantee", grant.grantee_id)
            if grant.task_id != self.task.id:
                raise PydanticCustomError(
                    "scenario_grant_task_mismatch",
                    "Grant task_id 必须与 Scenario task.id 相同",
                )
        return self

    @model_validator(mode="after")
    def validate_oracle_references(self) -> Self:
        """校验 Oracle 目标、来源和撤销 Skill 均已声明。"""
        declared_assets = frozenset(asset.id for asset in self.assets)
        declared_skills = frozenset(skill.id for skill in self.skills)
        declared_selectors = frozenset(selector.alias for selector in self.effect_selectors)
        declared_artifacts = frozenset(
            output.alias
            for session in self.sessions
            for step in session.steps
            for output in step.outputs
        )
        for expectation in self.oracle.expected_origins:
            self._validate_target(expectation.target.root, declared_artifacts, declared_selectors)
            for origin in expectation.origins:
                declared = declared_assets if origin.root.startswith("asset:") else declared_skills
                if origin.identifier not in declared:
                    self._undeclared("origin", origin.root)

        persistence = self.oracle.expected_persistence
        if persistence is not None and persistence.revoked_skill not in declared_skills:
            self._undeclared("revoked skill", persistence.revoked_skill)
        return self

    @model_validator(mode="after")
    def validate_counterfactual_references(self) -> Self:
        """校验反事实引用只观察同一 Scenario 内声明。"""
        declared_selectors = frozenset(selector.alias for selector in self.effect_selectors)
        declared_artifacts = frozenset(
            output.alias
            for session in self.sessions
            for step in session.steps
            for output in step.outputs
        )
        for counterfactual in self.counterfactuals:
            if counterfactual.target.alias not in declared_artifacts:
                self._undeclared("artifact alias", counterfactual.target.root)
            if counterfactual.observe.alias not in declared_selectors:
                self._undeclared("effect selector", counterfactual.observe.root)
        return self

    @staticmethod
    def _reject_duplicates(*groups: tuple[str, tuple[str, ...]]) -> None:
        for kind, values in groups:
            repeated = _duplicates(values)
            if repeated:
                raise PydanticCustomError(
                    "scenario_duplicate_id",
                    "{kind} 存在重复 ID: {ids}",
                    {"kind": kind, "ids": ", ".join(repeated)},
                )

    @staticmethod
    def _undeclared(kind: str, value: str) -> None:
        raise PydanticCustomError(
            "scenario_reference_undeclared",
            "{kind} 引用了未声明值: {value}",
            {"kind": kind, "value": value},
        )

    @classmethod
    def _validate_target(
        cls,
        target: str,
        artifacts: frozenset[str],
        selectors: frozenset[str],
    ) -> None:
        if target.startswith("artifact:"):
            if target.removeprefix("artifact:") not in artifacts:
                cls._undeclared("artifact alias", target)
        elif target.removeprefix("effect-selector:") not in selectors:
            cls._undeclared("effect selector", target)
