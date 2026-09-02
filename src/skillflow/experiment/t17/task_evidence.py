"""T17 任务成功的 Run/Session/Artifact/Effect/Receipt 强绑定证据。"""

from pathlib import Path
from typing import Annotated, Literal, Never, Self, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.benchmark.runner import ScenarioRunResult
from skillflow.experiment.t17.scenario_registry import T17ScenarioMeasurement
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EventType
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_research import (
    ArtifactSha256Assertion,
    EffectReceiptedAssertion,
)
from skillflow.store.event_store import EventStore
from skillflow.validation import validate_yaml_document

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class TaskArtifactEvidence(StrictModel):
    """一个 required task alias 的存在性与内容 commitment。"""

    alias: NonEmptyStr
    present: bool
    artifact_id: NonEmptyStr | None = None
    content_sha256: Sha256Hex | None = None
    expected_content_sha256: Sha256Hex | None = None
    matches_expected: bool
    session_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_presence_binding(self) -> Self:
        """present=true 必须同时绑定 ID、hash 和 Session。"""
        values = (self.artifact_id, self.content_sha256, self.session_id)
        if self.present is not all(item is not None for item in values):
            raise PydanticCustomError(
                "t17_task_artifact_binding",
                "Artifact present 与 ID/hash/Session 绑定不一致",
            )
        expected_match = self.present and (
            self.expected_content_sha256 is None
            or self.content_sha256 == self.expected_content_sha256
        )
        if self.matches_expected is not expected_match:
            raise PydanticCustomError(
                "t17_task_artifact_commitment",
                "Artifact matches_expected 与 commitment 不一致",
            )
        return self


class TaskEffectEvidence(StrictModel):
    """一个 required task Effect 的执行与 Receipt 绑定。"""

    selector_alias: NonEmptyStr
    present: bool
    effect_id: NonEmptyStr | None = None
    receipt_id: NonEmptyStr | None = None
    session_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_presence_binding(self) -> Self:
        """present=true 必须同时绑定 Effect、Receipt 与 Session。"""
        values = (self.effect_id, self.receipt_id, self.session_id)
        if self.present is not all(item is not None for item in values):
            raise PydanticCustomError(
                "t17_task_effect_binding",
                "Effect present 与 Effect/Receipt/Session 绑定不一致",
            )
        return self


class T17TaskSuccessEvidence(StrictModel):
    """确定性 evaluator 的完整任务证据，而不是调用方裸布尔值。"""

    schema_version: Literal["0.1"] = "0.1"
    evaluator_id: Literal["skillflow-t17-task-success-evaluator"] = (
        "skillflow-t17-task-success-evaluator"
    )
    evaluator_version: Literal["1.0.0"] = "1.0.0"
    run_id: NonEmptyStr
    scenario_id: NonEmptyStr
    task_success: bool
    required_artifact_aliases: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    required_effect_aliases: tuple[NonEmptyStr, ...]
    artifacts: Annotated[tuple[TaskArtifactEvidence, ...], Field(min_length=1)]
    effects: tuple[TaskEffectEvidence, ...]
    reached_session_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    evidence_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_complete_success_evidence(self) -> Self:
        """成功只能由全部 required Artifact/Effect 证据机械推出。"""
        artifact_aliases = tuple(item.alias for item in self.artifacts)
        effect_aliases = tuple(item.selector_alias for item in self.effects)
        if artifact_aliases != self.required_artifact_aliases:
            self._invalid("required Artifact alias 与证据顺序不一致")
        if effect_aliases != self.required_effect_aliases:
            self._invalid("required Effect alias 与证据顺序不一致")
        expected = all(item.matches_expected for item in self.artifacts) and all(
            item.present for item in self.effects
        )
        if self.task_success is not expected:
            self._invalid("task_success 必须等于 required 证据的合取")
        return self

    @staticmethod
    def _invalid(detail: str) -> Never:
        raise PydanticCustomError("t17_task_success_evidence_invalid", detail)


class TaskEvidenceBuildError(ValueError):
    """标准 Run 缺少可评估任务结果。"""

    __slots__ = ("run_id",)

    def __init__(self, run_id: str) -> None:
        """保存 Run ID，并保留 Exception traceback 可写语义。"""
        super().__init__(run_id)
        self.run_id = run_id

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return f"{self.run_id}:task_success_not_evaluable"


def build_task_success_evidence(
    result: ScenarioRunResult,
    specification: T17ScenarioMeasurement,
    store: EventStore,
) -> T17TaskSuccessEvidence:
    """从 Runner alias、EventStore 与标准 Effect 报告机械构造任务证据。"""
    reported = result.risk_report.task_success
    if reported is None:
        raise TaskEvidenceBuildError(result.run_id)
    scenario = validate_yaml_document(Path(specification.scenario.root), Scenario)
    artifact_expectations = {}
    for assertion in scenario.success_assertions:
        match assertion:
            case ArtifactSha256Assertion(target=target, expected_sha256=expected_sha):
                artifact_expectations[target.alias] = expected_sha
            case EffectReceiptedAssertion():
                pass
            case unreachable:
                assert_never(unreachable)
    artifact_evidence = []
    for artifact_ref in specification.task_artifact_aliases:
        artifact_id = result.artifact_ids_by_alias.get(artifact_ref.alias)
        artifact = None if artifact_id is None else store.get_artifact(artifact_id)
        expected_content_sha256 = artifact_expectations.get(artifact_ref.alias)
        artifact_evidence.append(
            TaskArtifactEvidence(
                alias=artifact_ref.alias,
                present=artifact is not None,
                artifact_id=None if artifact is None else artifact.artifact_id,
                content_sha256=None if artifact is None else artifact.content_hash,
                expected_content_sha256=expected_content_sha256,
                matches_expected=(
                    artifact is not None
                    and (
                        expected_content_sha256 is None
                        or artifact.content_hash == expected_content_sha256
                    )
                ),
                session_id=(
                    None if artifact is None else artifact.observed_label.created_session_id
                ),
            )
        )
    effect_evidence = []
    for effect_ref in specification.task_required_effect_aliases:
        effect = next(
            (
                item
                for item in result.risk_report.effects
                if effect_ref.alias in item.selector_aliases
                or item.effect_alias == effect_ref.alias
            ),
            None,
        )
        effect_evidence.append(
            TaskEffectEvidence(
                selector_alias=effect_ref.alias,
                present=effect is not None,
                effect_id=None if effect is None else effect.effect_id,
                receipt_id=None if effect is None else effect.receipt_id,
                session_id=None if effect is None else effect.session_id,
            )
        )
    reached_sessions = tuple(
        dict.fromkeys(
            event.session_id
            for event in store.iter_run_events(result.run_id)
            if event.event_type is EventType.SESSION_START
        )
    )
    task_success = all(item.matches_expected for item in artifact_evidence) and all(
        item.present for item in effect_evidence
    )
    if reported is not task_success:
        raise TaskEvidenceBuildError(result.run_id)
    artifact_evidence_ids = tuple(
        item.artifact_id for item in artifact_evidence if item.artifact_id is not None
    )
    effect_evidence_ids = tuple(
        value
        for item in effect_evidence
        for value in (item.effect_id, item.receipt_id)
        if value is not None
    )
    return T17TaskSuccessEvidence(
        run_id=result.run_id,
        scenario_id=result.scenario_id,
        task_success=task_success,
        required_artifact_aliases=tuple(item.alias for item in specification.task_artifact_aliases),
        required_effect_aliases=tuple(
            item.alias for item in specification.task_required_effect_aliases
        ),
        artifacts=tuple(artifact_evidence),
        effects=tuple(effect_evidence),
        reached_session_ids=reached_sessions,
        evidence_ids=(
            *artifact_evidence_ids,
            *effect_evidence_ids,
            *reached_sessions,
        ),
    )
