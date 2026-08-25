from pathlib import Path

from skillflow.pilot.openclaw_plan import OpenClawToolName, compile_openclaw_plan


def test_g0_plan_preserves_sessions_skills_memory_and_safe_sink() -> None:
    plan = compile_openclaw_plan(Path("scenarios/benign/g0_legal_cross_skill.yaml"))

    assert plan.scenario_id == "G0"
    assert tuple(item.skill_id for item in plan.skills) == ("memory-skill-a", "memory-skill-b")
    assert tuple(item.session_id for item in plan.invocations) == (
        "session-0",
        "session-0",
        "session-1",
        "session-1",
    )
    tool_names = tuple(
        call.tool for invocation in plan.invocations for call in invocation.tool_calls
    )
    assert OpenClawToolName.WRITE in tool_names
    assert OpenClawToolName.READ in tool_names
    assert OpenClawToolName.SAFE_SINK in tool_names
    assert plan.target_effect_aliases == ("memory-send",)
    assert plan.expected_origin_ids == ("asset:memory-payload",)


def test_m2_plan_keeps_revocation_as_benchmark_control_fact() -> None:
    plan = compile_openclaw_plan(Path("scenarios/attacks/m2_revoked_memory_residual.yaml"))

    assert tuple(item.skill_id for item in plan.revocations) == ("memory-skill-a",)
    assert tuple(item.session_id for item in plan.revocations) == ("session-0",)
    assert plan.target_effect_aliases == ("residual-send-1", "residual-send-3")


def test_b0_file_read_is_bound_to_the_declared_effect_selector() -> None:
    plan = compile_openclaw_plan(Path("scenarios/benign/b0_legal_summary.yaml"))

    target_resources = tuple(item for item in plan.resources if item.effect_alias == "report-read")
    assert len(target_resources) == 1
    assert target_resources[0].relative_path == "documents/report.md"
    assert target_resources[0].origin_ids == ("asset:report",)
