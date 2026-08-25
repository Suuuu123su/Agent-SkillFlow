"""决策与追加式安全事件。"""

from datetime import datetime

from pydantic import Field, JsonValue

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Decision, EnforcementMode, EventType


class DecisionRecord(StrictModel):
    """同时保留基线、策略、授权和执行四个事实。"""

    decision_id: NonEmptyStr
    request_event_id: NonEmptyStr
    enforcement_mode: EnforcementMode
    baseline_result: Decision
    policy_result: Decision
    authorized: bool
    executed: bool
    manifest_id: NonEmptyStr | None = None
    decision_basis_artifact_ids: tuple[NonEmptyStr, ...] = ()
    matched_grant_ids: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()


class SecurityEvent(StrictModel):
    """一次不可原地修改的安全事件。"""

    event_id: NonEmptyStr
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    session_id: NonEmptyStr
    call_id: NonEmptyStr | None = None
    timestamp: datetime
    event_type: EventType
    actor_id: NonEmptyStr
    input_artifact_ids: tuple[NonEmptyStr, ...] = ()
    output_artifact_ids: tuple[NonEmptyStr, ...] = ()
    requested_effect: CapabilityEffect | None = None
    decision_id: NonEmptyStr | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
