"""Artifact 与来源标签。"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import ArtifactType, TrustLevel


class SecurityLabel(StrictModel):
    """只描述数据来源、不表达授权的标签。"""

    origins: frozenset[NonEmptyStr]
    trust: TrustLevel
    task_id: NonEmptyStr
    created_session_id: NonEmptyStr
    expiry: datetime | None = None
    revoked_origins: frozenset[NonEmptyStr] = frozenset()
    parent_artifact_ids: frozenset[NonEmptyStr] = frozenset()


class Artifact(StrictModel):
    """一个不可变的数据版本。"""

    artifact_id: NonEmptyStr
    artifact_type: ArtifactType
    content_hash: NonEmptyStr
    content_length: Annotated[int, Field(ge=0)]
    mime_type: NonEmptyStr
    created_by_event_id: NonEmptyStr
    observed_label: SecurityLabel
