"""最小 Matrix 与正常任务 v2 的冻结合同，不携带运行结果。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t17.contracts import HookName
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix import ExperimentMatrix
from skillflow.models.scenario_parts import EffectSelector

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
EXPECTED_CORE_COUNT = 23


class NormalArtifactRequirement(StrictModel):
    """普通任务输出的精确内容与 Session 合同。"""

    alias: NonEmptyStr
    expected_sha256: Sha256
    session_id: NonEmptyStr


class NormalEffectRequirement(StrictModel):
    """任务真正需要的资源/动作/Session，不读取风险 Golden。"""

    selector: EffectSelector
    session_id: NonEmptyStr
    rationale: NonEmptyStr


class NormalTaskContract(StrictModel):
    """新的功能性成功标准；风险判定是独立字段。"""

    evaluator_version: Literal["2.0.0"] = "2.0.0"
    scenario_id: NonEmptyStr
    scenario_path: NonEmptyStr
    scenario_sha256: Sha256
    task_id: NonEmptyStr
    artifacts: Annotated[tuple[NormalArtifactRequirement, ...], Field(min_length=1)]
    effects: tuple[NormalEffectRequirement, ...]
    risk_selectors: tuple[EffectSelector, ...]
    required_hooks: tuple[HookName, ...]
    benign_control: bool
    revision_rationale: NonEmptyStr

    @model_validator(mode="after")
    def validate_unique_requirements(self) -> Self:
        """不允许重复断言或缺少任务 Hook。"""
        aliases = tuple(item.alias for item in self.artifacts)
        if len(set(aliases)) != len(aliases):
            raise ValueError("normal_task_duplicate_artifact")
        effects = tuple(item.selector.alias for item in self.effects)
        if len(set(effects)) != len(effects):
            raise ValueError("normal_task_duplicate_effect")
        if HookName.TASK_SUCCESS not in self.required_hooks:
            raise ValueError("normal_task_hook_missing")
        return self


class GoldenOutcome(StrictModel):
    """运行前独立声明的任务与安全任务期望。"""

    variant: NonEmptyStr
    task_success: bool
    safe_task_success: bool


class MinimalConfiguration(StrictModel):
    """单语义实例、单主重复的最小技术验收，不授权付费。"""

    schema_version: Literal["1.0"] = "1.0"
    protocol_id: Literal["t17-minimal-technical-v1"] = "t17-minimal-technical-v1"
    semantic_instances: Literal[1] = 1
    primary_repeats: Literal[1] = 1
    matrix: ExperimentMatrix
    tasks: Annotated[tuple[NormalTaskContract, ...], Field(min_length=16, max_length=16)]
    replay_variants: tuple[NonEmptyStr, ...]
    replay_pairs_by_variant: dict[NonEmptyStr, Annotated[int, Field(ge=1)]]
    expected_replay_pairs: Annotated[int, Field(ge=1)]
    equivalent_task_pairs: tuple[tuple[NonEmptyStr, NonEmptyStr], ...]
    defense_pairs: tuple[tuple[NonEmptyStr, NonEmptyStr], ...]
    source_sha256: dict[NonEmptyStr, Sha256]
    golden: tuple[GoldenOutcome, ...]
    paid_api_calls_allowed: Literal[False] = False
    exclusions: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_bound_schedule(self) -> Self:
        """Matrix、任务、Replay 和独立 Golden 必须绑定同一调度。"""
        variants = {item.variant for item in self.matrix.variants}
        if len(variants) != EXPECTED_CORE_COUNT or self.matrix.determinism_repeats != 1:
            raise ValueError("minimal_matrix_requires_23_core_once")
        self._validate_task_pairs()
        self._validate_replays(variants)
        if {item.variant for item in self.golden} != variants or len(self.golden) != len(variants):
            raise ValueError("minimal_golden_schedule_drift")
        if any(not set(pair) <= variants for pair in self.defense_pairs):
            raise ValueError("minimal_defense_pair_missing")
        return self

    def _validate_task_pairs(self) -> None:
        paths = {item.scenario_path for item in self.tasks}
        if any(item.scenario.root not in paths for item in self.matrix.variants):
            raise ValueError("normal_task_contract_missing")
        tasks = {item.scenario_id: item for item in self.tasks}
        if len(tasks) != len(self.tasks):
            raise ValueError("normal_task_contract_duplicate")
        for left, right in self.equivalent_task_pairs:
            if left not in tasks or right not in tasks:
                raise ValueError("paired_normal_task_reference_missing")
            a, b = tasks[left], tasks[right]
            if a.artifacts != b.artifacts or a.effects != b.effects:
                raise ValueError("paired_normal_task_contract_drift")

    def _validate_replays(self, variants: set[str]) -> None:
        if set(self.replay_variants) != set(self.replay_pairs_by_variant):
            raise ValueError("minimal_replay_selection_drift")
        if len(set(self.replay_variants)) != len(self.replay_variants):
            raise ValueError("minimal_replay_duplicate")
        if not set(self.replay_variants) <= variants:
            raise ValueError("minimal_replay_unknown_variant")
        if sum(self.replay_pairs_by_variant.values()) != self.expected_replay_pairs:
            raise ValueError("minimal_replay_count_drift")
