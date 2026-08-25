import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillflow.models.enums import CapabilityAction, Lifetime, Scope
from skillflow.models.metrics import MetricStatus
from skillflow.pilot.errors import OpenClawPilotError
from skillflow.pilot.models import OpenClawEventKind, OpenClawRawEvent, PilotAdapterKind
from skillflow.pilot.openclaw_adapter import NodeOpenClawDriver, OpenClawPilotAdapter
from skillflow.pilot.openclaw_plan import compile_openclaw_plan
from skillflow.pilot.openclaw_plan_models import OpenClawScenarioPlan


def _context_event(sequence: int = 0) -> OpenClawRawEvent:
    return OpenClawRawEvent(
        schema_version="0.1",
        sequence=sequence,
        timestamp=datetime(2026, 8, 25, tzinfo=UTC),
        kind=OpenClawEventKind.CONTEXT_READ,
        run_id="openclaw-b0",
        task_id="task-b0",
        session_id="session-0",
        actor_id="summary-reader",
        platform_hook="llm_input",
    )


def _target_event(sequence: int = 1) -> OpenClawRawEvent:
    return OpenClawRawEvent(
        schema_version="0.1",
        sequence=sequence,
        timestamp=datetime(2026, 8, 25, tzinfo=UTC),
        kind=OpenClawEventKind.FILE_READ,
        run_id="openclaw-b0",
        task_id="task-b0",
        session_id="session-0",
        call_id="call-1",
        actor_id="summary-reader",
        platform_hook="after_tool_call",
        tool_name="read",
        resource="workspace:/documents/report.md",
        effect_alias="report-read",
        receipt_id="receipt-call-1",
        origin_ids=("asset:report",),
        executed=True,
        action=CapabilityAction.FILE_READ,
        source="workspace:/documents/report.md",
        sink="context:/task",
        scope=Scope.EXACT_FILE,
        lifetime=Lifetime.CALL,
        sensitivity=1,
        policy_fact="platform_executed_no_grant_fact",
    )


@dataclass
class JsonlDriver:
    events: tuple[OpenClawRawEvent, ...]
    plans: list[OpenClawScenarioPlan] = field(default_factory=list)

    def execute(self, plan: OpenClawScenarioPlan, output_root: Path) -> Path:
        self.plans.append(plan)
        output_root.mkdir(parents=True)
        path = output_root / "openclaw-events.jsonl"
        path.write_text(
            "".join(f"{event.model_dump_json()}\n" for event in self.events),
            encoding="utf-8",
        )
        return path


def test_openclaw_adapter_emits_unified_events_effect_and_receipt(tmp_path: Path) -> None:
    driver = JsonlDriver((_context_event(), _target_event()))
    output = tmp_path / "openclaw"

    observation = OpenClawPilotAdapter(driver).run(
        Path("scenarios/benign/b0_legal_summary.yaml"),
        output,
    )

    assert observation.adapter is PilotAdapterKind.OPENCLAW
    assert observation.scenario_id == "B0"
    assert len(observation.security_events) == 2
    assert observation.target_effects[0].receipt_id == "receipt-call-1"
    assert observation.provenance_recall.value == 1.0
    assert observation.missing_hooks == ("grant_matcher", "artifact_provenance_graph")
    assert driver.plans[0].scenario_id == "B0"
    assert (output / "security-events.jsonl").read_text(encoding="utf-8").count("\n") == 2
    assert (output / "observation.json").is_file()


def test_openclaw_adapter_marks_zero_target_denominator_as_na(tmp_path: Path) -> None:
    observation = OpenClawPilotAdapter(JsonlDriver((_context_event(),))).run(
        Path("scenarios/attacks/m2_revoked_memory_residual.yaml"),
        tmp_path / "openclaw",
    )

    assert observation.target_effects == ()
    assert observation.provenance_recall.status is MetricStatus.NOT_APPLICABLE
    assert observation.provenance_recall.value is None
    assert "skill_revocation_hook" in observation.missing_hooks


def _node_driver(tmp_path: Path) -> NodeOpenClawDriver:
    return NodeOpenClawDriver(
        node_path=Path("node"),
        openclaw_root=tmp_path / "openclaw-checkout",
        driver_path=Path("driver.ts"),
        plugin_path=Path("observer"),
    )


def test_node_driver_writes_request_and_uses_argument_array(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def completed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("skillflow.pilot.openclaw_adapter.subprocess.run", completed)
    plan = compile_openclaw_plan(Path("scenarios/benign/b0_legal_summary.yaml"))
    output = tmp_path / "evidence" / "openclaw"

    event_path = _node_driver(tmp_path).execute(plan, output)

    request_path = output.parent / "openclaw-request.json"
    assert '"scenario_id":"B0"' in request_path.read_text(encoding="utf-8").replace(" ", "")
    assert event_path == output / "openclaw-events.jsonl"
    command = captured["args"][0]
    assert isinstance(command, tuple)
    assert command[:3] == ("node", "--import", "tsx")
    assert captured["kwargs"]["check"] is False


def test_node_driver_rejects_existing_request_and_driver_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = compile_openclaw_plan(Path("scenarios/benign/b0_legal_summary.yaml"))
    output = tmp_path / "evidence" / "openclaw"
    output.parent.mkdir(parents=True)
    (output.parent / "openclaw-request.json").write_text("existing", encoding="utf-8")
    with pytest.raises(OpenClawPilotError, match="拒绝覆盖"):
        _node_driver(tmp_path).execute(plan, output)

    second = tmp_path / "second" / "openclaw"
    monkeypatch.setattr(
        "skillflow.pilot.openclaw_adapter.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=17, stdout="", stderr="driver boom"
        ),
    )
    with pytest.raises(OpenClawPilotError, match=r"17.*driver boom"):
        _node_driver(tmp_path).execute(plan, second)
