"""用原始响应恢复未完成任务；禁止新网络请求，并验证原运行的事件前缀不变。"""

# ruff: noqa: T201

import json
import shutil
import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from pydantic import SecretStr

from skillflow.experiment.t16.openai_responses import TransportResponse
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.api_models import ApiUsageEvent, V2LiveConfig
from skillflow.experiment.t17.v2.audited_transport import ResponseHeader, _token_usage
from skillflow.experiment.t17.v2.binding import validate_core_binding
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix, V2Trial
from skillflow.experiment.t17.v2.frozen import inside
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.live_client import V2LiveClient
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import CoreTerminal, PhaseContract
from skillflow.experiment.t17.v2.stage import StageSetup, _write_terminal
from skillflow.experiment.t17.v2.unit_execution import (
    CoreExecution,
    ExecutionContext,
    compact_id,
    execute_core,
    file_inventory,
)
from skillflow.experiment.t17.v2.usage_validation import journal_unit_usage
from skillflow.models.base import StrictModel


class ReconstructionNote(StrictModel):
    """记录恢复来源、原响应绑定与非在线耗时范围。"""

    source_raw: str
    source_unit_id: str
    source_response_ids: tuple[str, ...]
    source_response_event_ids: tuple[str, ...]
    original_event_prefix_length: int
    original_event_prefix_equal: bool = True
    payloads_and_call_bindings_equal: bool = True
    additional_network_requests: int = 0
    original_api_latency_ms: float
    local_reconstruction_wall_ms: float
    wall_latency_scope: str = (
        "恢复任务的 wall 值为本地恢复实测时间；原 API 等待时间另按原日志完整报告，"
        "不伪造原端到端耗时。"
    )
    interpretation: str = (
        "沿用真实模型响应，只有受信本地执行器恢复；不是新的独立模型采样。原失败记录仍保留。"
    )


class StoredResponses:
    """该对象没有联网实现或真实密钥，只能按原顺序返回完整一致的已有响应。"""

    def __init__(self, raw: Path, events: tuple[ApiUsageEvent, ...], endpoint: str) -> None:
        """绑定唯一来源、原顺序和固定接口地址。"""
        self.raw, self.events, self.endpoint = raw, events, endpoint
        self.position = 0

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> TransportResponse:
        """返回已保存响应；输入偏离原调用则直接拒绝。"""
        del headers
        if url != self.endpoint or self.position >= len(self.events):
            raise ValueError("recorded_core_would_require_new_request")
        event = self.events[self.position]
        record = json.loads(
            (self.raw / "api-private" / f"{event.attempt_index:06d}.json").read_text(
                encoding="utf-8"
            )
        )
        if payload != record["request"]:
            raise ValueError("recorded_core_original_request_changed")
        header = ResponseHeader.model_validate(record["response"])
        if (
            header.id != event.response_id
            or header.model != event.model_revision
            or header.status != event.response_status
            or _token_usage(header.usage) != event.usage
            or event.latency_ms is None
        ):
            raise ValueError("recorded_core_response_header_binding")
        self.position += 1
        return TransportResponse(200, record["response"], event.latency_ms)


def _events(database: Path) -> tuple[str, ...]:
    with sqlite3.connect(
        database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
    ) as connection:
        return tuple(
            row[0]
            for row in connection.execute("SELECT event_json FROM events ORDER BY sequence_number")
        )


def restore_recorded_core(
    setup: StageSetup, trial: V2Trial, directory: Path, source_relative: str
) -> CoreExecution:
    """不联网地恢复一个获准任务，并逐条保留原事件与用量。"""
    root = setup.project_root
    source = inside(root, source_relative)
    phase = read_model(source / "phase-contract.json", PhaseContract)
    original_config = read_model(source / "configuration.json", V2Configuration)
    original_matrix = read_model(source / "matrix.json", V2Matrix)
    original = read_model(
        source / "terminals" / (compact_id(trial.trial_id) + ".json"), CoreTerminal
    )
    if (
        original_config != setup.configuration
        or original_matrix != setup.matrix
        or original.status != "infrastructure_invalid"
        or original.reason != "V2UsageUnavailableError"
        or not original.usage.complete
    ):
        raise ValueError("recorded_core_source_not_approved_failure")
    source_rows = tuple(
        e for e in read_journal(source / "api-usage.jsonl") if e.unit_id == trial.trial_id
    )
    responses = tuple(e for e in source_rows if e.event_type == "response")
    if not responses or len(responses) != original.usage.responses:
        raise ValueError("recorded_core_response_coverage")
    directory.mkdir(parents=True, exist_ok=False)
    live = read_model(source.parent / "approved-live-config.json", V2LiveConfig)
    transport = StoredResponses(source, responses, live.endpoint)
    # 日志位于明确标注的离线重执行目录，不计作新增 API 调用，也不进入结果用量表。
    offline = directory / "local-reexecution-only"
    client = V2LiveClient(live, SecretStr("offline-reconstruction-no-real-credential"), transport)
    client.open_phase(offline, phase)
    client.begin_unit(trial.trial_id)
    execution = execute_core(
        ExecutionContext(root, directory, original_config, original_matrix, phase, client), trial
    )
    replayed = read_journal(offline / "api-usage.jsonl")
    rebound = tuple(e for e in replayed if e.event_type == "response")
    if transport.position != len(responses) or tuple(e.call for e in rebound) != tuple(
        e.call for e in responses
    ):
        raise ValueError("recorded_core_call_or_response_count_changed")
    core_directory = directory / "core" / compact_id(trial.trial_id)
    old_events = _events(source / "core" / compact_id(trial.trial_id) / "state.sqlite")
    new_events = _events(core_directory / "state.sqlite")
    if old_events != new_events[: len(old_events)]:
        raise ValueError("recorded_core_original_event_prefix_changed")
    note = ReconstructionNote(
        source_raw=source_relative,
        source_unit_id=trial.trial_id,
        source_response_ids=tuple(e.response_id for e in responses if e.response_id),
        source_response_event_ids=tuple(e.event_sha256 for e in responses),
        original_event_prefix_length=len(old_events),
        original_api_latency_ms=original.usage.latency_ms,
        local_reconstruction_wall_ms=execution.terminal.wall_latency_ms,
    )
    write_checked_json(core_directory / "reconstruction-provenance.json", note)
    core = execution.terminal.model_copy(
        update={
            "usage": journal_unit_usage(source_rows),
            "raw_files": file_inventory(directory, core_directory),
        }
    )
    validate_core_binding(original_config, core)
    if core.usage != original.usage or not any(
        d.behavior == "schema_rejection" for d in core.decisions
    ):
        raise ValueError("recorded_core_original_usage_or_failure_lost")
    write_checked_json(directory / "configuration.json", original_config)
    write_checked_json(directory / "matrix.json", original_matrix)
    write_checked_json(directory / "phase-contract.json", phase)
    # 原用量日志逐字保留；来源索引只选择本任务，不重复选择前 12 条任务的响应。
    shutil.copyfile(source / "api-usage.jsonl", directory / "api-usage.jsonl")
    _write_terminal(directory, core)
    return replace(execution, terminal=core)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    source = "runs/t17-v2-deepseek-20260904-01/model2/attempt-01/raw"
    config = read_model(root / source / "configuration.json", V2Configuration)
    matrix = read_model(root / source / "matrix.json", V2Matrix)
    phase = read_model(root / source / "phase-contract.json", PhaseContract)
    output = root / ".tmp/t17-deepseek-20260904-01/core13-reconstruction-check-01"
    setup = StageSetup(root, output, config, matrix, "live_reference", None, None, phase)
    recovered = restore_recorded_core(setup, matrix.trials[12], output, source)
    print("CORE13_RECOVERED_FROM_ORIGINAL_RESPONSES; ORIGINAL_EVENT_PREFIX_EQUAL; NEW_API=0")
    print(f"responses={recovered.terminal.usage.responses}; status={recovered.terminal.status}")
