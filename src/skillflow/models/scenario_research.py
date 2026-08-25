"""T12 场景配对、成功判据与研究预期合同。"""

from enum import StrEnum, unique
from typing import Annotated, Literal, Self, TypeAlias, assert_never

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.references import ArtifactAliasRef, EffectSelectorRef

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


@unique
class PairFactor(StrEnum):
    """良性/攻击配对中唯一允许变化的预注册因素。"""

    GRANT = "grant"
    SKILL_SEMANTICS = "skill_semantics"
    TOOL_RETURN_SEMANTICS = "tool_return_semantics"
    MEMORY_SEMANTICS = "memory_semantics"
    AUTHORIZATION_SOURCE = "authorization_source"
    SCOPE_TARGET = "scope_target"
    SESSION_BOUNDARY = "session_boundary"
    REVOCATION_RESIDUAL = "revocation_residual"


class ScenarioPairing(StrictModel):
    """一个场景与其能力匹配对照的稳定关系。"""

    pair_id: NonEmptyStr
    paired_scenario_id: NonEmptyStr
    factor: PairFactor


class CanarySpec(StrictModel):
    """只以 ID 与摘要引用测试 Canary，不把正文写入报告合同。"""

    id: NonEmptyStr
    asset_id: NonEmptyStr
    sha256: Sha256


class ArtifactSha256Assertion(StrictModel):
    """用内容摘要验证一个声明式输出。"""

    kind: Literal["artifact_sha256"]
    target: ArtifactAliasRef
    expected_sha256: Sha256


class EffectReceiptedAssertion(StrictModel):
    """验证 selector 是否命中带真实 Receipt 的已执行 Effect。"""

    kind: Literal["effect_receipted"]
    target: EffectSelectorRef
    expected: bool


SuccessAssertion: TypeAlias = Annotated[
    ArtifactSha256Assertion | EffectReceiptedAssertion,
    Field(discriminator="kind"),
]


@unique
class ExpectedMetricName(StrEnum):
    """T12 场景可以预注册的研究输出。"""

    UEA = "UEA"
    CAUSAL_IMPACT = "causal_impact"
    HIAA_RUN = "HIAA_run"
    ALR = "ALR"
    RIR_1 = "RIR_1"
    RIR_3 = "RIR_3"


@unique
class MetricExpectationKind(StrEnum):
    """不把 N/A 与数值零混同的封闭预期。"""

    ZERO = "zero"
    POSITIVE = "positive"
    NOT_APPLICABLE = "not_applicable"


class ExpectedMetric(StrictModel):
    """一个指标的方向预期或带理由的结构化 N/A。"""

    metric: ExpectedMetricName
    expectation: MetricExpectationKind
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_na_reason(self) -> Self:
        """N/A 必须说明适用边界，数值预期不得夹带 N/A 理由。"""
        match self.expectation:
            case MetricExpectationKind.NOT_APPLICABLE:
                if self.reason is None:
                    raise PydanticCustomError(
                        "metric_na_reason_missing",
                        "not_applicable 指标预期必须提供 reason",
                    )
            case MetricExpectationKind.ZERO | MetricExpectationKind.POSITIVE:
                pass
            case unreachable:
                assert_never(unreachable)
        return self


@unique
class InfluenceExpectationKind(StrEnum):
    """反事实预期只区分确认影响与明确无影响。"""

    CONFIRMED = "confirmed"
    NONE = "none"


class ExpectedInfluence(StrictModel):
    """Artifact 到目标 Effect 的预注册因果预期。"""

    source: ArtifactAliasRef
    target: EffectSelectorRef
    expectation: InfluenceExpectationKind


class ToolOutputAlias(StrictModel):
    """把一次白名单 Tool 数据输出绑定为 Scenario Artifact alias。"""

    action_id: NonEmptyStr
    output_index: Annotated[int, Field(ge=0)]
    alias: ArtifactAliasRef
