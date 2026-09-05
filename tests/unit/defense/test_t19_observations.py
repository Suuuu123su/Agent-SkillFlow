from pathlib import Path

import pytest

from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t19.core_metrics import core_metrics
from skillflow.experiment.t19.execution import ExecutionSetup, execute
from skillflow.experiment.t19.matrix import precheck
from skillflow.experiment.t19.observations import coverage, observations
from skillflow.experiment.t19.tasks import task_variant
from skillflow.models.enums import EventType

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("mechanism", ["M2", "A2"])
def test_control_steps_need_actual_events_and_are_not_missing_model_calls(
    tmp_path: Path, mechanism: str
) -> None:
    trial = next(t for t in precheck() if t.mechanism == mechanism and t.group == "Monitor")
    record, _ = execute(
        ExecutionSetup(ROOT, tmp_path, trial.trial_id, "fake_reference", trial.group),
        task_variant(ROOT, mechanism, trial.role, trial.template),
        V2FakeClient(),
    )
    legacy = core_metrics((trial,), (record,))["required_step_observation_coverage"]
    fixed = coverage((record,), complete=True)
    assert legacy.value is not None
    assert legacy.value < 1
    assert fixed["required_step_observation_coverage"].value == 1
    assert fixed["trusted_control_observation_coverage"].value == 1
    altered_facts = record.data.facts.model_copy(
        update={
            "events": tuple(
                e
                for e in record.data.facts.events
                if e.event_type not in {EventType.AUTH_GRANT, EventType.SKILL_REVOKE}
            )
        }
    )
    changed = record.model_copy(
        update={"data": record.data.model_copy(update={"facts": altered_facts})}
    )
    assert any(not row.observed for row in observations(changed))
