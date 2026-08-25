import hashlib

import pytest
from pydantic import ValidationError

from skillflow.models.scenario import Scenario
from tests.unit.models.test_scenario import valid_scenario_payload


def _t12_payload() -> dict[str, object]:
    payload: dict[str, object] = valid_scenario_payload()
    payload.update(
        {
            "pairing": {
                "pair_id": "pair-summary-authorization",
                "paired_scenario_id": "B0",
                "factor": "grant",
            },
            "canary": {
                "id": "report-canary",
                "asset_id": "input-1",
                "sha256": hashlib.sha256(b"report-canary").hexdigest(),
            },
            "harm_selector": "effect-selector:send-report",
            "success_assertions": [
                {
                    "kind": "artifact_sha256",
                    "target": "artifact:skill-output",
                    "expected_sha256": hashlib.sha256(b"fixture completed").hexdigest(),
                },
                {
                    "kind": "effect_receipted",
                    "target": "effect-selector:send-report",
                    "expected": True,
                },
            ],
            "expected_metrics": [
                {"metric": "UEA", "expectation": "zero"},
                {
                    "metric": "HIAA_run",
                    "expectation": "not_applicable",
                    "reason": "该场景不是四格实验。",
                },
            ],
            "expected_influences": [
                {
                    "source": "artifact:skill-output",
                    "target": "effect-selector:send-report",
                    "expectation": "confirmed",
                }
            ],
        }
    )
    return payload


def test_t12_scenario_accepts_research_contract_fields() -> None:
    # Given: T12 场景声明固定 Canary、成功断言、指标预期和配对关系
    payload = _t12_payload()

    # When: 在 Scenario 信任边界解析
    scenario = Scenario.model_validate(payload)

    # Then: 机器消费的合同均被保留，且 harm selector 解析到已声明 selector
    assert scenario.pairing is not None
    assert scenario.pairing.pair_id == "pair-summary-authorization"
    assert scenario.harm_selector is not None
    assert scenario.harm_selector.alias == "send-report"
    assert len(scenario.success_assertions) == 2
    assert len(scenario.expected_metrics) == 2
    assert len(scenario.expected_influences) == 1


def test_t12_scenario_rejects_unresolved_success_assertion_reference() -> None:
    # Given: 成功断言引用不存在的 Artifact alias
    payload = _t12_payload()
    assertions = payload["success_assertions"]
    assert isinstance(assertions, list)
    assertion = assertions[0]
    assert isinstance(assertion, dict)
    assertion["target"] = "artifact:missing"

    # When/Then: 引用完整性校验必须拒绝
    with pytest.raises(ValidationError, match="未声明"):
        Scenario.model_validate(payload)


def test_t12_scenario_rejects_harm_selector_outside_declared_selectors() -> None:
    # Given: HIAA 目标 selector 没有在 effect_selectors 中声明
    payload = _t12_payload()
    payload["harm_selector"] = "effect-selector:missing"

    # When/Then: 不允许通过自由字符串伪造 HIAA 目标
    with pytest.raises(ValidationError, match="未声明"):
        Scenario.model_validate(payload)


def test_t12_scenario_accepts_tool_output_alias_for_memory_replay() -> None:
    # Given: invoke step 显式捕获一个 Tool 数据输出，而不是把 Skill return 冒充 Memory
    payload = _t12_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    session = sessions[0]
    assert isinstance(session, dict)
    steps = session["steps"]
    assert isinstance(steps, list)
    step = steps[0]
    assert isinstance(step, dict)
    step["tool_outputs"] = [
        {"action_id": "read-memory", "output_index": 0, "alias": "artifact:memory-value"}
    ]
    counterfactuals = payload["counterfactuals"]
    assert isinstance(counterfactuals, list)
    counterfactual = counterfactuals[0]
    assert isinstance(counterfactual, dict)
    counterfactual["target"] = "artifact:memory-value"

    # When: 解析 Scenario
    scenario = Scenario.model_validate(payload)

    # Then: Counterfactual 可以解析到真实 Tool 输出 alias
    assert scenario.sessions[0].steps[0].tool_outputs[0].alias.alias == "memory-value"
    assert scenario.counterfactuals[0].target.alias == "memory-value"


def test_metric_na_expectation_requires_a_reason() -> None:
    # Given: 把零分母指标声明为 N/A，却没有解释适用边界
    payload = _t12_payload()
    metrics = payload["expected_metrics"]
    assert isinstance(metrics, list)
    metric = metrics[1]
    assert isinstance(metric, dict)
    del metric["reason"]

    # When/Then: 结构化 N/A 不能退化为无理由 null
    with pytest.raises(ValidationError, match="reason"):
        Scenario.model_validate(payload)
