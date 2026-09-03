"""核验 core 的步数、Hook、Fake 决策与授权链，而非信任汇总声明。"""

from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.t17.contracts import HookCapability, HookName, MeasurementStatus
from skillflow.experiment.t17.minimal.run_models import MinimalRunRecord
from skillflow.models.enums import EventType
from skillflow.models.scenario import Scenario
from skillflow.store.event_store import EventStore


def verify_record_bindings(store: EventStore, record: MinimalRunRecord, scenario: Scenario) -> None:
    """模型不能自己定义 Hook 覆盖、Step ID、Manifest 或 Grant 缺失原因。"""
    events = tuple(store.iter_run_events(record.run_id))
    invokes = tuple(item for item in events if item.event_type is EventType.SKILL_INVOKE)
    if record.step_event_ids != tuple(item.event_id for item in invokes):
        raise ValueError("minimal_step_event_binding")
    expected_hooks = tuple(
        HookCapability(
            hook=HookName.TASK_SUCCESS,
            required=True,
            available=True,
            status=MeasurementStatus.MEASURED,
            evidence_ids=record.task.evidence_ids,
        )
        if hook.hook is HookName.TASK_SUCCESS
        else hook
        for hook in record.runtime.hooks
    )
    if record.hooks != expected_hooks:
        raise ValueError("minimal_hook_evidence_binding")
    grants = {item.grant_id for item in store.iter_run_grants(record.run_id)}
    manifests = {item.id for item in scenario.skills}
    for observation in record.runtime.decisions:
        decision = store.get_decision(observation.decision_id)
        request = store.get_event(observation.request_event_id)
        if (
            decision is None
            or request is None
            or request.run_id != record.run_id
            or decision.manifest_id not in manifests
            or decision.manifest_id != request.actor_id
        ):
            raise ValueError("minimal_decision_manifest_binding")
        if not set(decision.matched_grant_ids) <= grants or (
            not decision.matched_grant_ids and not decision.reason_codes
        ):
            raise ValueError("minimal_grant_or_missing_reason_binding")
    if record.domain == "fake_reference":
        scripts, _ = t12_fixture_registry()
        bindings = {item.id: item.implementation.root for item in scenario.skills}
        for sequence, (invoke, journal) in enumerate(
            zip(invokes, record.decision_journal, strict=True), 1
        ):
            actions = tuple(item.action_id for item in scripts[bindings[invoke.actor_id]].actions)
            if (
                journal.sequence != sequence
                or journal.allowed_action_ids != actions
                or journal.selected_action_ids != actions
                or journal.behavior != "normal"
                or not journal.schema_valid
            ):
                raise ValueError("minimal_fixed_fake_journal_binding")
