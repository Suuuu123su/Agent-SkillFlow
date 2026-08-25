"""真实 Harness Pilot 的严格输入与报告模型。"""

from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import CapabilityAction, Lifetime, Scope
from skillflow.models.events import SecurityEvent
from skillflow.models.metrics import RatioMetric
from skillflow.models.resources import ResourceRef

NonNegativeInt = Annotated[int, Field(ge=0)]
Sensitivity = Annotated[int, Field(ge=0, le=4)]


@unique
class PilotAdapterKind(StrEnum):
    """参与 T15 比较的两个 Adapter。"""

    MOCK = "mock"
    OPENCLAW = "openclaw"


@unique
class ProvenanceBasis(StrEnum):
    """Pilot 来源比例的统计单位，禁止跨口径直接作差。"""

    GRAPH_WIDE_ARTIFACTS = "graph-wide-artifacts"
    TARGET_EFFECT_LABELS = "target-effect-labels"


@unique
class OpenClawEventKind(StrEnum):
    """观察插件允许输出的封闭事件集合。"""

    CONTEXT_READ = "context_read"
    SKILL_LOAD = "skill_load"
    SKILL_INVOKE = "skill_invoke"
    SKILL_RETURN = "skill_return"
    SKILL_REVOKE = "skill_revoke"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    FILE_READ = "file_read"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    SAFE_EFFECT = "safe_effect"


EFFECT_KINDS = frozenset(
    {
        OpenClawEventKind.FILE_READ,
        OpenClawEventKind.MEMORY_READ,
        OpenClawEventKind.MEMORY_WRITE,
        OpenClawEventKind.SAFE_EFFECT,
    }
)
SKILL_KINDS = frozenset(
    {
        OpenClawEventKind.SKILL_LOAD,
        OpenClawEventKind.SKILL_INVOKE,
        OpenClawEventKind.SKILL_RETURN,
        OpenClawEventKind.SKILL_REVOKE,
    }
)


class OpenClawRawEvent(StrictModel):
    """OpenClaw JSONL 到统一模型之间的唯一信任边界。"""

    schema_version: Literal["0.1"]
    sequence: NonNegativeInt
    timestamp: datetime
    kind: OpenClawEventKind
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    session_id: NonEmptyStr
    actor_id: NonEmptyStr
    platform_hook: NonEmptyStr
    call_id: NonEmptyStr | None = None
    skill_id: NonEmptyStr | None = None
    tool_name: NonEmptyStr | None = None
    resource: ResourceRef | None = None
    effect_alias: NonEmptyStr | None = None
    receipt_id: NonEmptyStr | None = None
    origin_ids: tuple[NonEmptyStr, ...] = ()
    executed: bool | None = None
    action: CapabilityAction | None = None
    source: ResourceRef | None = None
    sink: ResourceRef | None = None
    scope: Scope | None = None
    lifetime: Lifetime | None = None
    sensitivity: Sensitivity | None = None
    policy_fact: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_kind_specific_evidence(self) -> Self:
        """执行事实必须完整，非 Effect 事件不能携带半个 Effect。"""
        if self.kind in EFFECT_KINDS:
            required = (
                self.receipt_id,
                self.action,
                self.sink,
                self.scope,
                self.lifetime,
                self.sensitivity,
                self.policy_fact,
            )
            if self.executed is not True or any(item is None for item in required):
                raise PydanticCustomError(
                    "openclaw_effect_evidence_missing",
                    "executed OpenClaw Effect requires receipt and complete effect facts",
                )
        elif any(
            item is not None
            for item in (
                self.effect_alias,
                self.receipt_id,
                self.executed,
                self.action,
                self.source,
                self.sink,
                self.scope,
                self.lifetime,
                self.sensitivity,
                self.policy_fact,
            )
        ):
            raise PydanticCustomError(
                "openclaw_non_effect_has_effect_fields",
                "non-effect OpenClaw event cannot carry effect facts",
            )
        if self.kind in SKILL_KINDS and self.skill_id is None:
            raise PydanticCustomError(
                "openclaw_skill_id_missing",
                "skill event requires skill_id",
            )
        return self


class PilotEffectEvidence(StrictModel):
    """两个 Adapter 共用的目标 Effect 比较单元。"""

    effect_alias: NonEmptyStr
    action: CapabilityAction
    receipt_id: NonEmptyStr
    origin_ids: tuple[NonEmptyStr, ...]
    policy_fact: NonEmptyStr


class PilotObservation(StrictModel):
    """一个 Scenario 在一个 Adapter 上的观察结果。"""

    adapter: PilotAdapterKind
    scenario_id: NonEmptyStr
    security_events: tuple[SecurityEvent, ...]
    target_effects: tuple[PilotEffectEvidence, ...]
    provenance_recall: RatioMetric
    provenance_basis: ProvenanceBasis
    missing_hooks: tuple[NonEmptyStr, ...] = ()


class PilotScenarioComparison(StrictModel):
    """Mock 与 OpenClaw 的逐场景差异。"""

    scenario_id: NonEmptyStr
    mock_effect_count: NonNegativeInt
    openclaw_effect_count: NonNegativeInt
    effect_count_match: bool
    mock_provenance_recall: RatioMetric
    openclaw_provenance_recall: RatioMetric
    mock_provenance_basis: ProvenanceBasis
    openclaw_provenance_basis: ProvenanceBasis
    provenance_basis_match: bool
    provenance_delta: float | None
    policy_match: bool
    differences: tuple[NonEmptyStr, ...]


class PilotReport(StrictModel):
    """T15 三场景正式报告。"""

    schema_version: Literal["0.1"] = "0.1"
    openclaw_commit: NonEmptyStr
    comparisons: tuple[PilotScenarioComparison, ...]
    real_credentials_used: bool
    external_effects_replaced: bool
    production_state_modified: bool
