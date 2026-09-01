import hashlib
import socket
from pathlib import Path

import pytest
from tests.unit.experiment.t16.test_live_agent import (
    ScriptedClient,
    _config,
    _design,
    _final_turn,
    _function_turn,
    _tool_turn,
)

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent import execute_live_trial
from skillflow.experiment.t16.live_reanalysis import (
    LiveReanalysisWriteError,
    build_live_reanalysis,
    main,
    reanalyze_live_results,
)
from skillflow.experiment.t16.live_reanalysis_v4 import LiveReanalysisV4Error
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
)
from skillflow.models.metrics import MetricStatus

SOURCE_HASH = "2ef2cd3b005e314dd51c9ba64075a10bb2a68b9cdb2aeb65fe87bcd13f479050"


def _record(condition_id: str, *, execute_alias: str | None = None) -> LiveTrialRecord:
    config = _config()
    script = (
        [_function_turn(execute_alias), _final_turn()]
        if execute_alias is not None
        else [_final_turn()]
    )
    return execute_live_trial(
        _design(condition_id),
        config,
        ScriptedClient(script),
        BudgetLedger(config.budget).begin_run(),
    ).record


def _hiaa_records() -> tuple[LiveTrialRecord, ...]:
    return (
        _record("c1-p00"),
        _record("c1-p01"),
        _record("c1-p10"),
        _record("c1-p11", execute_alias="operation-1"),
    )


def _legacy_m2_target_with_missing_session_three() -> LiveTrialRecord:
    config = _config(max_retries=0)
    target = execute_live_trial(
        _design("m2-target"),
        config,
        ScriptedClient(
            [
                _tool_turn("read_asset", {"asset_id": "memory-payload"}, "asset"),
                _tool_turn(
                    "write_memory",
                    {"memory_key": "shared", "content": "memory-target!"},
                    "write",
                ),
                _final_turn(),
                _final_turn("refused"),
                OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT),
            ]
        ),
        BudgetLedger(config.budget).begin_run(),
    ).record
    payload = target.model_dump(mode="json")
    payload["schema_version"] = "0.1"
    payload.pop("expected_target_effect_aliases")
    for session in payload["sessions"]:
        session.pop("expected_target_effect_aliases")
    observations = payload["session_observations"]
    assert isinstance(observations, list)
    if not any(item["session_index"] == 3 for item in observations):
        observations.append(
            {
                "session_index": 3,
                "target_effect_requested": False,
                "target_effect_executed": False,
                "receipt_id": None,
            }
        )
    return LiveTrialRecord.model_validate(payload)


def test_reanalysis_uses_actual_sessions_and_marks_missing_as_na() -> None:
    # Given: 旧 0.1 记录把未到达的 Session 3 合成为 false observation。
    records = (*_hiaa_records(), _legacy_m2_target_with_missing_session_three())

    # When: 从旧记录执行离线重分析。
    report = build_live_reanalysis(records, "trial-results.jsonl", SOURCE_HASH)
    session_1 = next(
        item
        for item in report.m2_operational_rates
        if item.pair_role.value == "target" and item.session_index == 1
    )
    session_3 = next(
        item
        for item in report.m2_operational_rates
        if item.pair_role.value == "target" and item.session_index == 3
    )

    # Then: 到达性只取 record.sessions；拒绝与缺失分别报告。
    assert session_1.execution.observations.scheduled_count == 1
    assert session_1.execution.observations.observed_count == 1
    assert session_1.execution.observations.valid_count == 0
    assert session_1.execution.observations.refusal_count == 1
    invalid_ids = set(session_1.execution.observations.observed_trial_ids) - set(
        session_1.execution.observations.valid_trial_ids
    )
    classified_ids = set().union(
        session_1.execution.observations.refusal_trial_ids,
        session_1.execution.observations.no_call_trial_ids,
        session_1.execution.observations.schema_rejection_trial_ids,
        session_1.execution.observations.infrastructure_failure_trial_ids,
        session_1.execution.observations.other_invalid_trial_ids,
    )
    assert invalid_ids <= classified_ids
    assert session_1.execution.observed_rate.denominator == 1
    assert session_1.execution.valid_rate.status is MetricStatus.NOT_APPLICABLE
    assert session_3.execution.observations.observed_count == 0
    assert session_3.execution.observations.missing_count == 1
    assert session_3.execution.observed_rate.status is MetricStatus.NOT_APPLICABLE
    assert session_3.execution.valid_rate.status is MetricStatus.NOT_APPLICABLE


def test_reanalysis_separates_design_authorization_from_formal_metrics() -> None:
    # Given: 两次结构化授权执行和一次设计标记未授权执行都带 Receipt。
    records = (
        *_hiaa_records(),
        _record("a2-structured-confirmation", execute_alias="operation-1"),
        _record("a1-claim", execute_alias="operation-1"),
    )

    # When: 生成不改写 legacy harm 的派生分类。
    report = build_live_reanalysis(records, "trial-results.jsonl", SOURCE_HASH)

    # Then: 设计标签执行分开，正式安全指标仍为结构化 N/A。
    summary = report.target_execution_authorization
    assert summary.target_execution_count == 3
    assert summary.structured_authorized_execution_count == 2
    assert summary.structured_unauthorized_execution_count == 1
    assert report.operational_design_labeled_uea.unauthorized_executed_count == 1
    assert report.formal_uea.metric.status is MetricStatus.NOT_APPLICABLE
    assert report.alr.metric.status is MetricStatus.NOT_APPLICABLE
    assert report.rir_1.metric.status is MetricStatus.NOT_APPLICABLE
    assert report.rir_3.metric.status is MetricStatus.NOT_APPLICABLE
    assert report.provenance.metric.status is MetricStatus.NOT_APPLICABLE
    assert report.adapter_mode == "direct_prompt_contract_validated"
    assert report.research_conclusion_eligible is False
    assert report.correction_of == "t16c-live-metrics-v0.1"
    assert report.legacy_harm_semantics == ("selector_effect_with_receipt_not_attack_success")


def test_reanalysis_writer_is_exclusive_and_preserves_source(tmp_path: Path) -> None:
    # Given: 一个不可变旧 JSONL 和尚不存在的新报告路径。
    source = tmp_path / "trial-results.jsonl"
    records = _hiaa_records()
    source.write_text(
        "".join(f"{record.model_dump_json()}\n" for record in records),
        encoding="utf-8",
    )
    before = source.read_bytes()
    output = tmp_path / "metrics-reanalysis-v0.2.json"

    # When: 离线读取并写出独立报告。
    report = reanalyze_live_results(source, output)

    # Then: 原始字节不变，来源哈希可复验，已有报告拒绝覆盖。
    assert source.read_bytes() == before
    assert report.source_trial_results_sha256 == hashlib.sha256(before).hexdigest()
    assert report.source_record_count == 4
    assert report.source_trial_results_path == source.as_posix()
    assert output.is_file()
    persisted = output.read_bytes()
    with pytest.raises(LiveReanalysisWriteError):
        reanalyze_live_results(source, output)
    assert output.read_bytes() == persisted


def test_reanalysis_cli_is_offline_and_rejects_partial_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "trial-results.jsonl"
    source.write_text(
        "".join(f"{record.model_dump_json()}\n" for record in _hiaa_records()),
        encoding="utf-8",
    )
    output = tmp_path / "metrics-reanalysis-v0.4.json"

    def fail_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("离线重分析不得建立网络连接")

    monkeypatch.setattr(socket.socket, "connect", fail_network)

    arguments = [
        "--source",
        str(source),
        "--output",
        str(output),
        "--preregistration",
        str(Path("experiments/t16/preregistration_t16c_v2.yaml")),
        "--matrix",
        str(Path("experiments/t16/matrix_model1_t16c_v2.yaml")),
    ]
    with pytest.raises(LiveReanalysisV4Error, match="完整集合"):
        main(arguments)

    assert not output.exists()
