"""完整模拟响应经过真实记账接口，跨模型和防御报告只作零费用软件验证。"""

import json
from collections.abc import Mapping
from pathlib import Path

from pydantic import SecretStr

from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.openai_responses import TransportResponse
from skillflow.experiment.t17.live_matrix import T17LiveStage, load_live_preregistration
from skillflow.experiment.t17.v2.api_models import V2LiveConfig
from skillflow.experiment.t17.v2.campaign_usage import journal_totals
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.dataset_analysis import dataset_reports
from skillflow.experiment.t17.v2.live_client import V2LiveClient
from skillflow.experiment.t17.v2.loading import load_stage
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage


class SimulatedResponses:
    """不建立网络；使用固定返回 Token 验证响应账本绑定。"""

    def __init__(self) -> None:
        self.calls = 0

    def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonObject
    ) -> TransportResponse:
        self.calls += 1
        content = json.loads(payload["input"][1]["content"][0]["text"])
        output = {
            "selected_action_ids": content["allowed_action_ids"],
            "output_text": content["installed_skill_expected_output"],
        }
        body = {
            "id": f"response_simulated_{self.calls}",
            "model": payload["model"],
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "message_simulated",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(output)}],
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 30,
                "total_tokens": 130,
                "input_tokens_details": {"cached_tokens": 20},
                "output_tokens_details": {"reasoning_tokens": 10},
            },
        }
        return TransportResponse(200, body, 5)


def test_24_18_simulated_api_usage_is_bound_to_every_actual_call(t17_cli_root: Path) -> None:
    root = Path.cwd()
    target = t17_cli_root / "simulated-api"
    config, bundles = build_configuration(root, target / "config")
    write_configuration(root, target / "config", config, bundles)
    matrix = build_matrix(root, config, T17LiveStage.CANARY)
    old = load_live_preregistration(root / "experiments/t17/preregistration.yaml")
    client_config = V2LiveConfig(
        provider=matrix.provider,
        budget=old.model1_budget.model_copy(update={"allow_live": True}),
        matrix_sha256=model_digest(matrix),
        cost_plan_sha256="b" * 64,
        approval_id="local-simulation-only",
        prompt_cache_mode="explicit",
    )
    transport = SimulatedResponses()
    client = V2LiveClient(client_config, SecretStr("simulated-not-a-real-key"), transport)
    updates = []
    result = run_stage(
        StageSetup(
            root, target / "attempt", config, matrix, "fake_reference", client, updates.append
        )
    )
    assert result.gate.passed, result.gate.failures
    assert len(result.cores) == 24
    assert len(result.replays) == 18
    loaded = load_stage(root, target / "attempt")
    totals = journal_totals(loaded.api_usage)
    assert totals.api_calls == totals.responses == transport.calls > 24
    assert totals.input_tokens == 100 * transport.calls
    assert totals.output_tokens == 20 * transport.calls
    assert totals.reasoning_tokens == 10 * transport.calls
    assert totals.latency_ms == 5 * transport.calls
    assert updates[-1].terminal_core == 24
    assert updates[-1].terminal_replay == 18
    assert updates[-1].usage.api_calls == transport.calls
    decisions = {
        (u.identity.unit_id, d.run_id, d.session_id, d.step_id, d.call_id)
        for u in (*result.cores, *result.replays)
        for d in u.decisions
    }
    calls = {
        (e.unit_id, e.call.run_id, e.call.session_id, e.call.step_id, e.call.call_id)
        for e in loaded.api_usage
        if e.event_type == "response"
    }
    assert decisions == calls


def test_model_and_21_base_defense_pairing_end_to_end(t17_cli_root: Path) -> None:
    root = Path.cwd()
    target = t17_cli_root / "comparison-e2e"
    config, bundles = build_configuration(root, target / "config")
    # 只缩小软件集成测试的抽样次数，正式冻结矩阵仍是五簇、每簇三次。
    config = config.model_copy(update={"templates": config.templates[:1], "repeats": 1})
    write_configuration(root, target / "config", config, bundles)
    loaded = []
    for stage in (T17LiveStage.MODEL1, T17LiveStage.MODEL2, T17LiveStage.DEFENSE):
        matrix = build_matrix(root, config, stage)
        output = target / stage.value
        result = run_stage(StageSetup(root, output, config, matrix, "scripted", None))
        assert result.gate.passed, (stage, result.gate.failures)
        loaded.append(load_stage(root, output))
    assert [(len(s.result.cores), len(s.result.replays)) for s in loaded] == [
        (24, 18),
        (24, 18),
        (18, 18),
    ]
    reports = dataset_reports(tuple(loaded))
    model = [c for c in reports.comparisons if c.kind == "model"]
    defense = [c for c in reports.comparisons if c.kind == "defense"]
    assert len(model) == 25
    assert len(defense) == 22
    assert all(c.complete for c in (*model, *defense))
    combined = next(c for c in defense if c.report_id == "monitor-vs-enforce")
    assert combined.left.scheduled_core == combined.right.scheduled_core == 21
    assert len(combined.left.identity.raw_manifest_sha256) == 2
    gain = combined.named_deltas["security_gain.uea_count"]
    assert (
        gain.value
        == combined.left.metrics["uea_count"].value - combined.right.metrics["uea_count"].value
    )
    assert (
        combined.named_deltas["utility_loss"].value
        == combined.left.metrics["task_success"].value
        - combined.right.metrics["task_success"].value
    )
    assert all(row.interval_agreement == "indeterminate" for row in model[0].comparisons)
