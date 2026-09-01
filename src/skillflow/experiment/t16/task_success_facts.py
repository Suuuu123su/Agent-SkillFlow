"""平台生成的任务产物、Receipt、Session Trace 与安全 commitment。"""

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Self

from pydantic import Field, JsonValue, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.task_success_evidence import Sha256Hex
from skillflow.experiment.t16.task_success_output import StructuredTaskResultV3
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]


def commitment_sha256(value: JsonValue) -> str:
    """对结构化值进行固定 JSON 编码并计算平台 commitment。"""
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def payload_commitment_sha256(payload: bytes) -> str:
    """只返回 payload 哈希，调用方无需保存正文。"""
    return hashlib.sha256(payload).hexdigest()


class PlatformArtifactRecord(StrictModel):
    """平台 Artifact registry 中不含正文的可复核记录。"""

    artifact_id: NonEmptyStr
    artifact_alias: NonEmptyStr
    artifact_content_sha256: Sha256Hex
    run_id: NonEmptyStr
    trial_id: NonEmptyStr
    session_id: NonEmptyStr
    producer_step: NonNegativeInt
    valid_schema_ids: tuple[NonEmptyStr, ...]
    structured_field_commitments: dict[str, Sha256Hex]
    structured_set_commitments: dict[str, Sha256Hex]


class PlatformReceiptRecord(StrictModel):
    """绑定 Run、Session 与 Safe Sink commitment 的平台 Receipt。"""

    effect_id: NonEmptyStr
    effect_alias: NonEmptyStr
    receipt_id: NonEmptyStr
    run_id: NonEmptyStr
    session_id: NonEmptyStr
    safe_sink_commitment_sha256: Sha256Hex

    @classmethod
    def create(
        cls,
        request: "ReceiptRegistrationRequest",
        payload: bytes,
    ) -> "PlatformReceiptRecord":
        """由平台元数据生成 ID；payload 只在调用栈内参与哈希。"""
        material = (
            f"{request.run_id}:{request.session_id}:"
            f"{request.effect_alias}:{request.receipt_ordinal}"
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return cls(
            effect_id=f"effect-{digest[:24]}",
            effect_alias=request.effect_alias,
            receipt_id=f"receipt-{digest[24:48]}",
            run_id=request.run_id,
            session_id=request.session_id,
            safe_sink_commitment_sha256=payload_commitment_sha256(payload),
        )


class PlatformSessionTrace(StrictModel):
    """平台接受的 Tool 顺序，不使用模型自然语言总结。"""

    session_id: NonEmptyStr
    reached: bool
    accepted_tool_sequence: tuple[NonEmptyStr, ...]


class PlatformEvidenceSnapshot(StrictModel):
    """一次 evaluator 调用可见的平台事实快照。"""

    artifact_registry_available: bool
    receipt_registry_available: bool
    session_trace_available: bool
    artifacts: tuple[PlatformArtifactRecord, ...] = ()
    receipts: tuple[PlatformReceiptRecord, ...] = ()
    sessions: tuple[PlatformSessionTrace, ...] = ()

    @model_validator(mode="after")
    def require_unique_platform_identities(self) -> Self:
        """拒绝平台身份或 alias 冲突。"""
        identities = (
            tuple(item.artifact_id for item in self.artifacts),
            tuple(item.artifact_alias for item in self.artifacts),
            tuple(item.receipt_id for item in self.receipts),
            tuple(item.effect_id for item in self.receipts),
            tuple(item.session_id for item in self.sessions),
        )
        if any(len(values) != len(set(values)) for values in identities):
            raise PydanticCustomError(
                "t16_platform_evidence_duplicate",
                "平台 Artifact、Receipt 或 Session 身份不得重复",
            )
        return self


@dataclass(frozen=True, slots=True)
class ArtifactRegistrationRequest:
    """平台而非模型提供的 Artifact 登记元数据。"""

    run_id: str
    trial_id: str
    session_id: str
    producer_step: int
    platform_alias: str


@dataclass(frozen=True, slots=True)
class ReceiptRegistrationRequest:
    """Receipt 的平台身份；payload 单独传递且不进入可序列化请求。"""

    run_id: str
    session_id: str
    effect_alias: str
    receipt_ordinal: int


class TaskResultArtifactRegistry:
    """由平台分配 alias、ID 和 commitment 的 Trial 私有注册表。"""

    def __init__(self) -> None:
        """创建空的 Trial 私有注册表。"""
        self._artifacts: dict[str, PlatformArtifactRecord] = {}

    def register_structured_result(
        self,
        request: ArtifactRegistrationRequest,
        result: StructuredTaskResultV3,
    ) -> PlatformArtifactRecord:
        """登记严格 v3 结果；模型对象中不存在 alias 或 hash 字段。"""
        if request.platform_alias in self._artifacts:
            raise PydanticCustomError(
                "t16_artifact_alias_duplicate",
                "平台 Artifact alias 不得重复登记",
            )
        content = result.model_dump(mode="json")
        content_sha = commitment_sha256(content)
        fact_id_values: list[JsonValue] = []
        fact_id_values.extend(sorted(result.fact_ids))
        identity = (
            f"{request.run_id}:{request.trial_id}:{request.session_id}:"
            f"{request.producer_step}:{content_sha}"
        )
        artifact = PlatformArtifactRecord(
            artifact_id=f"artifact-{hashlib.sha256(identity.encode()).hexdigest()[:24]}",
            artifact_alias=request.platform_alias,
            artifact_content_sha256=content_sha,
            run_id=request.run_id,
            trial_id=request.trial_id,
            session_id=request.session_id,
            producer_step=request.producer_step,
            valid_schema_ids=("task-result-v3",),
            structured_field_commitments={
                "schema_version": commitment_sha256(result.schema_version),
                "task_status": commitment_sha256(result.task_status.value),
                "result_kind": commitment_sha256(result.result_kind.value),
                "value_id": commitment_sha256(result.value_id),
            },
            structured_set_commitments={
                "fact_ids": commitment_sha256(fact_id_values),
            },
        )
        self._artifacts[request.platform_alias] = artifact
        return artifact

    @property
    def artifacts(self) -> tuple[PlatformArtifactRecord, ...]:
        """按平台登记顺序返回不可变快照。"""
        return tuple(self._artifacts.values())
