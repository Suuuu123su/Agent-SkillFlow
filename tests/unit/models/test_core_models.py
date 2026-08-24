from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from skillflow.models import (
    Artifact,
    ArtifactType,
    AuthorizationGrant,
    CapabilityEffect,
    Decision,
    DecisionRecord,
    EffectRecord,
    EventType,
    SecurityEvent,
    SecurityLabel,
    SkillManifest,
    TrustLevel,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_effect(*, lifetime: str = "call") -> CapabilityEffect:
    return CapabilityEffect.model_validate(
        {
            "source": "workspace:/report.txt",
            "action": "network.send",
            "sink": "mock://external",
            "scope": "exact-file",
            "lifetime": lifetime,
            "sensitivity": 4,
        }
    )


def make_grant(
    *, lifetime: str, session_id: str | None = None, call_id: str | None = None
) -> AuthorizationGrant:
    return AuthorizationGrant.model_validate(
        {
            "grant_id": "grant-1",
            "issuer_id": "user-1",
            "issuer_type": "user",
            "grantee_id": "skill-a",
            "action": "network.send",
            "source_pattern": "workspace:/report.txt",
            "sink_pattern": "mock://external",
            "scope": "exact-file",
            "lifetime": lifetime,
            "task_id": "task-1",
            "session_id": session_id,
            "call_id": call_id,
            "valid_from": NOW,
            "expires_at": NOW + timedelta(hours=1),
        }
    )


@pytest.mark.parametrize(
    ("lifetime", "session_id", "call_id"), [("call", None, None), ("session", None, None)]
)
def test_grant_requires_identifier_for_narrow_lifetime(
    lifetime: str,
    session_id: str | None,
    call_id: str | None,
) -> None:
    # Given: 一个 call/session Grant 缺少对应边界 ID
    # When/Then: Grant 在解析边界拒绝它
    with pytest.raises(ValidationError):
        make_grant(lifetime=lifetime, session_id=session_id, call_id=call_id)


def test_grant_rejects_skill_as_issuer() -> None:
    # Given: Skill 试图把自己声明为 Grant issuer
    payload = make_grant(lifetime="task").model_dump(mode="json")
    payload["issuer_type"] = "skill"

    # When/Then: 只有 user/trusted_policy 可以签发 Grant
    with pytest.raises(ValidationError):
        AuthorizationGrant.model_validate(payload)


def test_grant_rejects_expiry_not_after_valid_from() -> None:
    # Given: 一个在生效时刻已经过期的 Grant
    payload = make_grant(lifetime="task").model_dump(mode="json")
    payload["expires_at"] = payload["valid_from"]

    # When/Then: 时间窗口在边界被拒绝
    with pytest.raises(ValidationError):
        AuthorizationGrant.model_validate(payload)


def test_grant_json_round_trip_preserves_call_id() -> None:
    # Given: 一个带 call_id 的 call Grant
    grant = make_grant(lifetime="call", call_id="call-7")

    # When: 经过 JSON 往返
    restored = AuthorizationGrant.model_validate_json(grant.model_dump_json())

    # Then: 所有字段无损且对象相等
    assert restored == grant
    assert restored.call_id == "call-7"


def test_unknown_action_and_lifetime_are_rejected() -> None:
    # Given: 一个未知 action 和一个未知 lifetime
    unknown_action = make_effect().model_dump(mode="json")
    unknown_action["action"] = "network.teleport"
    unknown_lifetime = make_effect().model_dump(mode="json")
    unknown_lifetime["lifetime"] = "forever"

    # When/Then: 两个封闭枚举都拒绝未知值
    with pytest.raises(ValidationError):
        CapabilityEffect.model_validate(unknown_action)
    with pytest.raises(ValidationError):
        CapabilityEffect.model_validate(unknown_lifetime)


def test_executed_effect_requires_result_and_receipt() -> None:
    # Given: 一个声称已执行但没有结果或 Receipt 的 EffectRecord
    # When/Then: 不能把请求误报为已执行效果
    with pytest.raises(ValidationError):
        EffectRecord(
            effect_id="effect-1",
            effect=make_effect(),
            request_event_id="event-request",
            decision_id="decision-1",
            executed=True,
        )


def test_manifest_cannot_embed_grant_or_issuer_identity() -> None:
    # Given: Skill Manifest 试图携带 issuer_type
    payload = {
        "schema_version": "0.1",
        "id": "skill-a",
        "principal_type": "skill",
        "issuer_type": "user",
        "requested_permissions": [make_effect().model_dump(mode="json")],
    }

    # When/Then: 未知授权字段被拒绝，Manifest 不能生成 Grant
    with pytest.raises(ValidationError):
        SkillManifest.model_validate(payload)


def test_artifact_decision_and_event_round_trip_without_field_loss() -> None:
    # Given: 完整 Artifact、DecisionRecord 和带 call_id 的 SecurityEvent
    label = SecurityLabel(
        origins=frozenset({"skill-a"}),
        trust=TrustLevel.USER,
        task_id="task-1",
        created_session_id="session-1",
    )
    artifact = Artifact(
        artifact_id="artifact-1",
        artifact_type=ArtifactType.CONTEXT,
        content_hash="sha256:abc",
        content_length=3,
        mime_type="text/plain",
        created_by_event_id="event-0",
        observed_label=label,
    )
    decision = DecisionRecord(
        decision_id="decision-1",
        request_event_id="event-1",
        enforcement_mode="monitor",
        baseline_result=Decision.ALLOW,
        policy_result=Decision.DENY,
        authorized=False,
        executed=True,
        decision_basis_artifact_ids=(artifact.artifact_id,),
    )
    event = SecurityEvent(
        event_id="event-1",
        run_id="run-1",
        task_id="task-1",
        session_id="session-1",
        call_id="call-7",
        timestamp=NOW,
        event_type=EventType.TOOL_CALL_REQUEST,
        actor_id="skill-a",
        input_artifact_ids=(artifact.artifact_id,),
        requested_effect=make_effect(),
        decision_id=decision.decision_id,
        metadata={"fixture": True},
    )

    # When: 三个模型分别经过 JSON 往返
    restored_artifact = Artifact.model_validate_json(artifact.model_dump_json())
    restored_decision = DecisionRecord.model_validate_json(decision.model_dump_json())
    restored_event = SecurityEvent.model_validate_json(event.model_dump_json())

    # Then: 所有模型相等且 call_id 保留
    assert restored_artifact == artifact
    assert restored_decision == decision
    assert restored_event == event
    assert restored_event.call_id == "call-7"
