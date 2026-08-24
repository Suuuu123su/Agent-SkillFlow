"""结构化授权 Grant。"""

from datetime import datetime
from typing import Literal, Self, assert_never

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import CapabilityAction, Lifetime, PrincipalType
from skillflow.models.resources import ResourceRef


class AuthorizationGrant(StrictModel):
    """由用户或可信策略签发的能力授权。"""

    grant_id: NonEmptyStr
    issuer_id: NonEmptyStr
    issuer_type: Literal[PrincipalType.USER, PrincipalType.TRUSTED_POLICY]
    grantee_id: NonEmptyStr
    action: CapabilityAction
    source_pattern: ResourceRef | None
    sink_pattern: ResourceRef
    scope: NonEmptyStr
    lifetime: Lifetime
    task_id: NonEmptyStr
    session_id: NonEmptyStr | None = None
    call_id: NonEmptyStr | None = None
    valid_from: datetime
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_boundaries(self) -> Self:
        """校验 lifetime 所需 ID 和授权时间窗口。"""
        match self.lifetime:
            case Lifetime.CALL:
                if self.call_id is None:
                    raise PydanticCustomError(
                        "grant_call_id_missing",
                        "call lifetime 要求 call_id",
                    )
            case Lifetime.TASK:
                pass
            case Lifetime.SESSION:
                if self.session_id is None:
                    raise PydanticCustomError(
                        "grant_session_id_missing",
                        "session lifetime 要求 session_id",
                    )
            case Lifetime.PERSISTENT:
                pass
            case _ as unreachable:
                assert_never(unreachable)

        if self.expires_at is not None and self.expires_at <= self.valid_from:
            raise PydanticCustomError(
                "grant_time_window_invalid",
                "expires_at 必须晚于 valid_from",
            )
        return self
