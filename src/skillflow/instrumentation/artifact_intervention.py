"""结构保持的 Artifact identity/neutral 派生。"""

import json
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import assert_never

from pydantic import JsonValue, TypeAdapter

from skillflow.instrumentation.errors import HarnessStateError
from skillflow.models.enums import EventType
from skillflow.models.provenance import Artifact
from skillflow.runtime.session import ActorCall, ArtifactEmission, RuntimeRecorder

JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


@unique
class ArtifactInterventionMode(StrEnum):
    """配对分支固定使用的两种派生模式。"""

    IDENTITY = "identity"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class ArtifactInterventionResult:
    """结构守恒检查所需的原始与派生 Artifact 证据。"""

    mode: ArtifactInterventionMode
    original: Artifact
    derived: Artifact
    schema_preserved: bool


def intervene_artifact(
    recorder: RuntimeRecorder,
    source_artifact_id: str,
    mode: ArtifactInterventionMode,
) -> ArtifactInterventionResult:
    """追加一个等长同类型派生版本，不改写或删除源 Artifact。"""
    source = recorder.require_artifact(source_artifact_id)
    content = recorder.read_content(source_artifact_id)
    derived_content, schema_preserved = _intervention_content(content, source.mime_type, mode)
    derived = recorder.record_artifact(
        ArtifactEmission(
            event_type=EventType.ARTIFACT_DERIVE,
            artifact_type=source.artifact_type,
            content=derived_content,
            actor=ActorCall("harness:counterfactual", None),
            input_artifact_ids=(source_artifact_id,),
            origins=source.observed_label.origins,
            trust=source.observed_label.trust,
            mime_type=source.mime_type,
            metadata={"intervention": mode.value},
        )
    )
    return ArtifactInterventionResult(mode, source, derived, schema_preserved)


def _intervention_content(
    content: bytes,
    mime_type: str,
    mode: ArtifactInterventionMode,
) -> tuple[bytes, bool]:
    if mode is ArtifactInterventionMode.IDENTITY:
        return content, True
    if not content:
        raise HarnessStateError("neutralize_artifact", "zero-length artifact has no neutral form")
    if mime_type == "application/json":
        value = JSON_VALUE_ADAPTER.validate_json(content)
        neutral_value = _neutral_json(value)
        if not _same_json_shape(value, neutral_value):
            raise HarnessStateError("neutralize_artifact", "neutral JSON changed structure")
        encoded = json.dumps(
            neutral_value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=False,
        ).encode()
        if len(encoded) > len(content):
            raise HarnessStateError("neutralize_artifact", "neutral JSON exceeds source length")
        return encoded + (b" " * (len(content) - len(encoded))), True
    if mime_type.startswith("text/"):
        return b" " * len(content), True
    return bytes(len(content)), True


def _neutral_json(value: JsonValue) -> JsonValue:
    match value:
        case None:
            neutral: JsonValue = None
        case bool():
            neutral = False
        case int():
            neutral = 0
        case float():
            neutral = 0.0
        case str():
            neutral = "x" * len(value)
        case list():
            neutral = [_neutral_json(item) for item in value]
        case dict():
            neutral = {key: _neutral_json(item) for key, item in value.items()}
        case _ as unreachable:
            assert_never(unreachable)
    return neutral


def _same_json_shape(original: JsonValue, neutral: JsonValue) -> bool:
    if type(original) is not type(neutral):
        return False
    match original:
        case None:
            same = neutral is None
        case bool():
            same = isinstance(neutral, bool)
        case int():
            same = isinstance(neutral, int)
        case float():
            same = isinstance(neutral, float)
        case str():
            same = isinstance(neutral, str)
        case list():
            same = (
                isinstance(neutral, list)
                and len(original) == len(neutral)
                and all(
                    _same_json_shape(left, right)
                    for left, right in zip(original, neutral, strict=True)
                )
            )
        case dict():
            same = (
                isinstance(neutral, dict)
                and tuple(original) == tuple(neutral)
                and all(_same_json_shape(original[key], neutral[key]) for key in original)
            )
        case _ as unreachable:
            assert_never(unreachable)
    return same
