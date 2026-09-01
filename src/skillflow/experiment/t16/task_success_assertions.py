"""T16-D.1 无动态执行能力的任务成功断言白名单。"""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from skillflow.experiment.t16.task_success_evidence import (
    Sha256Hex,
    TaskSuccessAssertionType,
)
from skillflow.models.base import NonEmptyStr, StrictModel


class TaskSuccessAssertionBase(StrictModel):
    """所有白名单断言共享的身份字段。"""

    assertion_id: NonEmptyStr
    required: bool = True


class ArtifactExistsAssertion(TaskSuccessAssertionBase):
    """要求平台 registry 中存在指定 alias 的 Artifact。"""

    assertion_type: Literal[TaskSuccessAssertionType.ARTIFACT_EXISTS] = (
        TaskSuccessAssertionType.ARTIFACT_EXISTS
    )
    artifact_alias: NonEmptyStr


class ArtifactAliasResolvesAssertion(TaskSuccessAssertionBase):
    """要求平台 alias 唯一解析到 Artifact ID。"""

    assertion_type: Literal[TaskSuccessAssertionType.ARTIFACT_ALIAS_RESOLVES] = (
        TaskSuccessAssertionType.ARTIFACT_ALIAS_RESOLVES
    )
    artifact_alias: NonEmptyStr


class ArtifactSchemaValidAssertion(TaskSuccessAssertionBase):
    """要求平台已确认 Artifact 通过指定 Schema。"""

    assertion_type: Literal[TaskSuccessAssertionType.ARTIFACT_SCHEMA_VALID] = (
        TaskSuccessAssertionType.ARTIFACT_SCHEMA_VALID
    )
    artifact_alias: NonEmptyStr
    schema_id: NonEmptyStr


class ArtifactStructuredFieldEqualsAssertion(TaskSuccessAssertionBase):
    """比较结构化字段的平台 commitment。"""

    assertion_type: Literal[TaskSuccessAssertionType.ARTIFACT_STRUCTURED_FIELD_EQUALS] = (
        TaskSuccessAssertionType.ARTIFACT_STRUCTURED_FIELD_EQUALS
    )
    artifact_alias: NonEmptyStr
    field_path: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    expected_value_commitment_sha256: Sha256Hex


class ArtifactStructuredSetEqualsAssertion(TaskSuccessAssertionBase):
    """比较结构化集合的平台 commitment。"""

    assertion_type: Literal[TaskSuccessAssertionType.ARTIFACT_STRUCTURED_SET_EQUALS] = (
        TaskSuccessAssertionType.ARTIFACT_STRUCTURED_SET_EQUALS
    )
    artifact_alias: NonEmptyStr
    field_path: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    expected_value_commitment_sha256: Sha256Hex


class ArtifactContentCommitmentMatchesAssertion(TaskSuccessAssertionBase):
    """比较完整 Artifact 的平台内容 commitment。"""

    assertion_type: Literal[TaskSuccessAssertionType.ARTIFACT_CONTENT_COMMITMENT_MATCHES] = (
        TaskSuccessAssertionType.ARTIFACT_CONTENT_COMMITMENT_MATCHES
    )
    artifact_alias: NonEmptyStr
    expected_value_commitment_sha256: Sha256Hex


class RequiredReceiptExistsAssertion(TaskSuccessAssertionBase):
    """要求指定合法 Effect 存在平台 Receipt。"""

    assertion_type: Literal[TaskSuccessAssertionType.REQUIRED_RECEIPT_EXISTS] = (
        TaskSuccessAssertionType.REQUIRED_RECEIPT_EXISTS
    )
    effect_alias: NonEmptyStr
    session_id: NonEmptyStr | None = None


class ReceiptBoundToRunAssertion(TaskSuccessAssertionBase):
    """要求 Receipt 与当前 Run 绑定。"""

    assertion_type: Literal[TaskSuccessAssertionType.RECEIPT_BOUND_TO_RUN] = (
        TaskSuccessAssertionType.RECEIPT_BOUND_TO_RUN
    )
    effect_alias: NonEmptyStr


class ReceiptBoundToSessionAssertion(TaskSuccessAssertionBase):
    """要求 Receipt 与预注册 Session 绑定。"""

    assertion_type: Literal[TaskSuccessAssertionType.RECEIPT_BOUND_TO_SESSION] = (
        TaskSuccessAssertionType.RECEIPT_BOUND_TO_SESSION
    )
    effect_alias: NonEmptyStr
    session_id: NonEmptyStr


class SafeSinkCommitmentMatchesAssertion(TaskSuccessAssertionBase):
    """比较 Safe Sink 生成的 payload commitment。"""

    assertion_type: Literal[TaskSuccessAssertionType.SAFE_SINK_COMMITMENT_MATCHES] = (
        TaskSuccessAssertionType.SAFE_SINK_COMMITMENT_MATCHES
    )
    effect_alias: NonEmptyStr
    session_id: NonEmptyStr | None = None
    expected_value_commitment_sha256: Sha256Hex


class RequiredSessionReachedAssertion(TaskSuccessAssertionBase):
    """要求平台 Trace 显示到达指定 Session。"""

    assertion_type: Literal[TaskSuccessAssertionType.REQUIRED_SESSION_REACHED] = (
        TaskSuccessAssertionType.REQUIRED_SESSION_REACHED
    )
    session_id: NonEmptyStr


class RequiredToolSequenceObservedAssertion(TaskSuccessAssertionBase):
    """要求平台 Trace 按序观察到合法 Tool 序列。"""

    assertion_type: Literal[TaskSuccessAssertionType.REQUIRED_TOOL_SEQUENCE_OBSERVED] = (
        TaskSuccessAssertionType.REQUIRED_TOOL_SEQUENCE_OBSERVED
    )
    session_id: NonEmptyStr
    expected_tool_sequence: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


TaskSuccessAssertion = Annotated[
    ArtifactExistsAssertion
    | ArtifactAliasResolvesAssertion
    | ArtifactSchemaValidAssertion
    | ArtifactStructuredFieldEqualsAssertion
    | ArtifactStructuredSetEqualsAssertion
    | ArtifactContentCommitmentMatchesAssertion
    | RequiredReceiptExistsAssertion
    | ReceiptBoundToRunAssertion
    | ReceiptBoundToSessionAssertion
    | SafeSinkCommitmentMatchesAssertion
    | RequiredSessionReachedAssertion
    | RequiredToolSequenceObservedAssertion,
    Field(discriminator="assertion_type"),
]

TASK_SUCCESS_ASSERTIONS_ADAPTER = TypeAdapter(tuple[TaskSuccessAssertion, ...])
