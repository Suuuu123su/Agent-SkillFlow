"""逐步骤观测覆盖v1.1：模型与受信控制器的证据都计入，不能补造事件。"""

from skillflow.experiment.t17.v2.measurements import measure
from skillflow.experiment.t17.v2.statistics_models import Measurement
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.models.base import StrictModel
from skillflow.models.enums import EventType
from skillflow.models.scenario_parts import ScenarioStep, StepAction


class StepObservation(StrictModel):
    """模型合法失败也有观测；缺真实控制事件则保持未观测。"""

    unit_id: str
    session_id: str
    step_id: str
    action: str
    observed: bool
    reason: str
    evidence_ids: tuple[str, ...]


def observations(core: CoreRecord) -> tuple[StepObservation, ...]:
    """控制事件同时匹配会话、可信主体及目标，不能借自动卸载冒充步骤。"""
    rows = []
    for session in core.data.analysis_definition.sessions:
        for step in session.steps:
            identifiers = _step_evidence(core, session.id, step)
            rows.append(
                StepObservation(
                    unit_id=core.unit_id,
                    session_id=session.id,
                    step_id=step.id,
                    action=step.action.value,
                    observed=bool(identifiers),
                    reason="recorded_execution_or_explicit_model_failure"
                    if identifiers
                    else "missing_step_evidence",
                    evidence_ids=identifiers,
                )
            )
    return tuple(rows)


def _step_evidence(core: CoreRecord, session: str, step: ScenarioStep) -> tuple[str, ...]:
    if step.action is StepAction.INVOKE_SKILL:
        decisions = tuple(
            d.call_id for d in core.decisions if d.step_id == step.id and d.session_id == session
        )
        issues = (
            *[i.run_id for i in core.issues if i.step_id == step.id and i.session_id == session],
            *[
                i.run_id
                for i in core.boundary_issues
                if i.step_id == step.id and i.session_id == session
            ],
        )
        limits = tuple(i.call_id for i in core.limits if i.step_id == step.id)
        return tuple(dict.fromkeys((*decisions, *issues, *limits)))
    events = tuple(e for e in core.data.facts.events if e.session_id == session)
    if step.action is StepAction.USER_CONFIRM and step.grant is not None:
        return tuple(
            e.event_id
            for e in events
            if e.event_type is EventType.AUTH_GRANT
            and e.actor_id == step.grant.issuer_id
            and e.metadata.get("grant_id") == step.grant.grant_id
            and step.grant in core.data.facts.grants
        )
    kind = {
        StepAction.REVOKE_SKILL: EventType.SKILL_REVOKE,
        StepAction.UNLOAD_SKILL: EventType.SKILL_UNLOAD,
    }.get(step.action)
    return tuple(
        e.event_id
        for e in events
        if e.event_type is kind
        and step.actor is not None
        and e.actor_id == step.actor.value
        and e.metadata.get("skill_id") == step.skill
    )


def coverage(cores: tuple[CoreRecord, ...], *, complete: bool) -> dict[str, Measurement]:
    """修正仅补入已存在的受信控制事件，不改变分母或模型任务成功。"""
    rows = tuple(row for core in cores for row in observations(core))
    evidence = tuple(c.unit_id for c in cores)
    controls = tuple(row for row in rows if row.action != StepAction.INVOKE_SKILL.value)
    return {
        "required_step_observation_coverage": measure(
            sum(r.observed for r in rows),
            len(rows),
            evidence,
            complete=complete,
            scope="scheduled_model_and_trusted_controller_steps_v1.1",
        ),
        "trusted_control_observation_coverage": measure(
            sum(r.observed for r in controls),
            len(controls),
            evidence,
            complete=complete,
            scope="trusted_revocation_confirmation_unload_steps",
        ),
    }
