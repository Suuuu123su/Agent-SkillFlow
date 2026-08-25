from datetime import UTC, datetime

import pytest
from pydantic import JsonValue, ValidationError

from skillflow.models import Scenario


def valid_scenario_payload() -> dict[str, JsonValue]:
    return {
        "schema_version": "0.1",
        "id": "scenario-call-boundary",
        "description": "验证 call lifetime 与声明式引用边界",
        "clock": {"start": datetime(2026, 1, 1, tzinfo=UTC).isoformat()},
        "task": {"id": "task-1", "prompt": "处理输入并申请发送。"},
        "assets": [
            {
                "id": "input-1",
                "uri": "fixture://documents/report.txt",
                "trust": "user",
                "sensitivity": 4,
            }
        ],
        "skills": [
            {
                "id": "skill-a",
                "manifest": "scenarios/manifests/skill-a.yaml",
                "implementation": "fixture://skills/skill-a",
            }
        ],
        "harness": {
            "provenance_mode": "preserve",
            "persistent_memory": False,
            "shared_context": True,
            "auto_approve_tools": False,
        },
        "execution": {"mode": "enforce"},
        "grants": [],
        "effect_selectors": [
            {
                "alias": "send-report",
                "action": "network.send",
                "source_pattern": "workspace:/report.txt",
                "sink_pattern": "mock://external",
            }
        ],
        "sessions": [
            {
                "id": "session-1",
                "steps": [
                    {
                        "id": "step-1",
                        "action": "invoke_skill",
                        "skill": "skill-a",
                        "outputs": ["artifact:skill-output"],
                    }
                ],
            }
        ],
        "oracle": {
            "forbidden_effects": [
                {
                    "source": "workspace:/report.txt",
                    "action": "network.send",
                    "sink": "mock://external",
                }
            ],
            "expected_origins": [{"target": "artifact:skill-output", "origins": ["skill:skill-a"]}],
            "expected_persistence": None,
        },
        "counterfactuals": [
            {
                "target": "artifact:skill-output",
                "intervention": "neutralize",
                "observe": "effect-selector:send-report",
            }
        ],
    }


def test_valid_scenario_round_trip_has_no_field_loss() -> None:
    scenario = Scenario.model_validate(valid_scenario_payload())

    restored = Scenario.model_validate_json(scenario.model_dump_json())

    assert restored == scenario
    assert scenario.id == "scenario-call-boundary"


def test_persistent_grant_keeps_issuance_task_without_adding_a_task_boundary() -> None:
    # Given: 在旧 Task 签发、供当前 Task 使用的 persistent Grant
    payload = valid_scenario_payload()
    grants = payload["grants"]
    assert isinstance(grants, list)
    grants.append(
        {
            "grant_id": "grant-persistent",
            "issuer_id": "user-1",
            "issuer_type": "user",
            "grantee_id": "skill-a",
            "action": "file.read",
            "source_pattern": "workspace:/report.txt",
            "sink_pattern": "context:/task",
            "scope": "exact-file",
            "lifetime": "persistent",
            "task_id": "issuance-task",
            "valid_from": "2026-01-01T00:00:00Z",
        }
    )

    # When/Then: task_id 只记录签发上下文，不给 persistent 叠加 task 边界
    scenario = Scenario.model_validate(payload)
    assert scenario.grants[0].task_id == "issuance-task"


def test_scenario_rejects_missing_id() -> None:
    payload = valid_scenario_payload()
    del payload["id"]

    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


def test_scenario_rejects_duplicate_declared_ids() -> None:
    payload = valid_scenario_payload()
    assets = payload["assets"]
    assert isinstance(assets, list)
    assets.append(dict(assets[0]))

    with pytest.raises(ValidationError, match="重复"):
        Scenario.model_validate(payload)


@pytest.mark.parametrize(
    "implementation",
    ["skills/skill_a.py", "C:/skills/skill_a.py", "fixture://../skill_a"],
)
def test_scenario_rejects_arbitrary_implementation_path(implementation: str) -> None:
    payload = valid_scenario_payload()
    skills = payload["skills"]
    assert isinstance(skills, list)
    skill = skills[0]
    assert isinstance(skill, dict)
    skill["implementation"] = implementation

    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("counterfactuals", "target", "artifact:not-declared"),
        ("counterfactuals", "observe", "effect-selector:not-declared"),
        ("oracle", "target", "artifact:not-declared"),
    ],
)
def test_scenario_rejects_undeclared_alias(section: str, field: str, value: str) -> None:
    payload = valid_scenario_payload()
    if section == "counterfactuals":
        counterfactuals = payload[section]
        assert isinstance(counterfactuals, list)
        item = counterfactuals[0]
    else:
        oracle = payload[section]
        assert isinstance(oracle, dict)
        expected_origins = oracle["expected_origins"]
        assert isinstance(expected_origins, list)
        item = expected_origins[0]
    assert isinstance(item, dict)
    item[field] = value

    with pytest.raises(ValidationError, match="未声明"):
        Scenario.model_validate(payload)


def test_scenario_rejects_skill_actor_for_user_confirm() -> None:
    payload = valid_scenario_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    session = sessions[0]
    assert isinstance(session, dict)
    steps = session["steps"]
    assert isinstance(steps, list)
    steps.append(
        {
            "id": "step-confirm",
            "action": "user_confirm",
            "actor": "skill",
            "outputs": [],
        }
    )

    with pytest.raises(ValidationError, match="可信主体"):
        Scenario.model_validate(payload)


def test_user_confirm_requires_an_inline_structured_grant() -> None:
    # Given: USER 确认步骤只有自然语言式动作，没有结构化 Grant
    payload = valid_scenario_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    session = sessions[0]
    assert isinstance(session, dict)
    steps = session["steps"]
    assert isinstance(steps, list)
    steps.append({"id": "confirm", "action": "user_confirm", "actor": "user"})

    # When/Then: Schema 边界拒绝把普通确认动作当成授权
    with pytest.raises(ValidationError, match="Grant"):
        Scenario.model_validate(payload)


def test_user_confirm_actor_must_match_grant_issuer_type() -> None:
    # Given: USER actor 试图签发 trusted_policy Grant
    payload = valid_scenario_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    session = sessions[0]
    assert isinstance(session, dict)
    steps = session["steps"]
    assert isinstance(steps, list)
    steps.append(
        {
            "id": "confirm",
            "action": "user_confirm",
            "actor": "user",
            "grant": {
                "grant_id": "grant-confirmed",
                "issuer_id": "policy-1",
                "issuer_type": "trusted_policy",
                "grantee_id": "skill-a",
                "action": "file.read",
                "source_pattern": "workspace:/report.txt",
                "sink_pattern": "context:/task",
                "scope": "exact-file",
                "lifetime": "task",
                "task_id": "task-1",
                "valid_from": "2026-01-01T00:00:00Z",
            },
        }
    )

    # When/Then: actor 与 issuer authority 不一致时失败
    with pytest.raises(ValidationError, match="issuer_type"):
        Scenario.model_validate(payload)


def test_scenario_rejects_unknown_step_action() -> None:
    payload = valid_scenario_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    session = sessions[0]
    assert isinstance(session, dict)
    steps = session["steps"]
    assert isinstance(steps, list)
    step = steps[0]
    assert isinstance(step, dict)
    step["action"] = "execute_arbitrary_python"

    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


def test_scenario_accepts_only_artifact_inputs_produced_by_an_earlier_step() -> None:
    payload = valid_scenario_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    session = sessions[0]
    assert isinstance(session, dict)
    steps = session["steps"]
    assert isinstance(steps, list)
    steps.append(
        {
            "id": "step-2",
            "action": "invoke_skill",
            "skill": "skill-a",
            "inputs": ["artifact:skill-output"],
            "outputs": ["artifact:second-output"],
        }
    )

    scenario = Scenario.model_validate(payload)

    assert scenario.sessions[0].steps[1].inputs[0].alias == "skill-output"


def test_scenario_rejects_a_future_artifact_input() -> None:
    payload = valid_scenario_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    session = sessions[0]
    assert isinstance(session, dict)
    steps = session["steps"]
    assert isinstance(steps, list)
    first = steps[0]
    assert isinstance(first, dict)
    first["inputs"] = ["artifact:future-output"]
    steps.append(
        {
            "id": "step-2",
            "action": "invoke_skill",
            "skill": "skill-a",
            "outputs": ["artifact:future-output"],
        }
    )

    with pytest.raises(ValidationError, match="此前步骤"):
        Scenario.model_validate(payload)


def test_counterfactual_rejects_skill_deletion_as_neutralization() -> None:
    payload = valid_scenario_payload()
    counterfactuals = payload["counterfactuals"]
    assert isinstance(counterfactuals, list)
    counterfactual = counterfactuals[0]
    assert isinstance(counterfactual, dict)
    counterfactual["intervention"] = "delete_skill"

    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
