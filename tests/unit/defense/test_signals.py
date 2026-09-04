from datetime import UTC, datetime

import pytest

from skillflow.defense.signals import SignalProjectionRequest, project_signals
from skillflow.experiment.t17.v2.fact_store import FactStore
from skillflow.experiment.t17.v2.portable_models import PortableRun
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import ArtifactType, Decision, EnforcementMode, EventType
from skillflow.models.events import SecurityEvent
from skillflow.models.provenance import Artifact
from skillflow.policy.models import AuthorizationBoundary, DecisionPlan
from skillflow.policy.runtime import PolicyToolRequest


def setup() -> tuple[FactStore, SignalProjectionRequest]:
    when = datetime(2026, 9, 4, tzinfo=UTC)
    source = Artifact.model_validate(
        {
            "artifact_id": "source",
            "artifact_type": "skill_output",
            "content_hash": "a" * 64,
            "content_length": 10,
            "mime_type": "text/plain",
            "created_by_event_id": "produce",
            "observed_label": {
                "origins": ["producer"],
                "trust": "untrusted",
                "task_id": "t",
                "created_session_id": "s",
            },
        }
    )
    effect = CapabilityEffect.model_validate(
        {
            "source": "context:/shared",
            "sink": "mock://sink",
            "action": "network.send",
            "scope": "exact-sink",
            "lifetime": "call",
            "sensitivity": 4,
        }
    )
    produce = SecurityEvent.model_validate(
        {
            "event_id": "produce",
            "run_id": "r",
            "task_id": "t",
            "session_id": "s",
            "timestamp": when,
            "event_type": "skill_return",
            "actor_id": "producer",
            "output_artifact_ids": ["source"],
        }
    )
    argument = source.model_copy(
        update={
            "artifact_id": "argument",
            "artifact_type": ArtifactType.TOOL_ARG,
            "created_by_event_id": "request",
        }
    )
    request = produce.model_copy(
        update={
            "event_id": "request",
            "event_type": EventType.TOOL_CALL_REQUEST,
            "actor_id": "consumer",
            "call_id": "c",
            "input_artifact_ids": ("source",),
            "output_artifact_ids": ("argument",),
            "requested_effect": effect,
        }
    )
    facts = PortableRun(
        run_id="r",
        events=(produce, request),
        artifacts=(source, argument),
        decisions=(),
        effects=(),
        grants=(),
        revocations=(),
        receipts=(),
    )
    base = DecisionPlan(
        EnforcementMode.MONITOR,
        Decision.ALLOW,
        Decision.DENY,
        authorized=False,
        executed=True,
        manifest_id="consumer",
        decision_basis_artifact_ids=("source", "argument"),
        matched_grant_ids=(),
        reason_codes=("USER_GRANT_MISSING",),
    )
    proposed = PolicyToolRequest(
        "allow",
        "consumer",
        "argument",
        effect,
        AuthorizationBoundary("t", "s", "c", when),
        (source,),
    )
    return FactStore(facts), SignalProjectionRequest("r", proposed, base, risk_target=True)


def test_projection_traces_predecision_events_only() -> None:
    store, request = setup()
    result = project_signals(store, request)
    assert result.signals.untrusted_context_in_basis
    assert result.signals.candidate_influence
    assert result.signals.grant_missing
    assert not result.signals.confirmed_influence
    assert not result.signals.target_effect_executed
    assert result.signals.evidence_availability["provenance"]
    assert set(result.signals.evidence_ids) == {"source", "produce", "request"}


def test_cross_run_request_rejected() -> None:
    store, request = setup()
    with pytest.raises(ValueError, match="request_binding"):
        project_signals(
            store,
            SignalProjectionRequest("another", request.request, request.base, risk_target=True),
        )
