"""T16-D.2 v3.1 Canary 的逐响应 fsync 用量日志。"""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from skillflow.experiment.t16.live_canary_usage_models import (
    CanaryUsageJournalEvent,
    CanaryUsageSnapshot,
    LiveCanaryMetadataDriftError,
    LiveCanaryUsageStoreError,
    usage_status,
)
from skillflow.experiment.t16.live_canary_usage_tracker import LiveCanaryUsageTracker
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.live_usage_store import (
    ActualUsageStatus,
    LiveTrialTerminalStatus,
)


class LiveCanaryUsageJournal:
    """新 Attempt 私有、追加式、逐响应同步的用量日志。"""

    def __init__(self, path: Path, config: T16CLiveConfig, protocol_id: str) -> None:
        """绑定新 Attempt 路径、冻结配置与协议身份。"""
        self.path = path
        self._config = config
        self._protocol_id = protocol_id
        self._config_sha256 = _canonical_sha256(config.model_dump(mode="json"))
        self._events: list[CanaryUsageJournalEvent] = []
        self._terminal_trials: set[str] = set()
        self._opened = False

    @property
    def config_sha256(self) -> str:
        """返回阶段执行配置的 canonical SHA-256。"""
        return self._config_sha256

    @property
    def expected_provider(self) -> str:
        """返回冻结 Provider。"""
        return "openai"

    @property
    def expected_model_id(self) -> str:
        """返回冻结模型 ID。"""
        return self._config.provider.model_id

    def open_new(self) -> None:
        """独占新建日志，绝不覆盖或续写旧 Attempt。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            detail = f"无法新建 Canary 用量日志: {self.path}"
            raise LiveCanaryUsageStoreError(detail) from error
        self._opened = True

    def start_trial(self, trial_id: str, condition_id: str) -> "LiveCanaryUsageTracker":
        """创建一条 Trial 私有的内存累计器。"""
        if not self._opened:
            detail = "Canary 用量日志尚未打开"
            raise LiveCanaryUsageStoreError(detail)
        if trial_id in self._terminal_trials:
            detail = f"Canary Trial 已存在终态: {trial_id}"
            raise LiveCanaryUsageStoreError(detail)
        return LiveCanaryUsageTracker(self, trial_id, condition_id)

    def append_snapshot(self, snapshot: CanaryUsageSnapshot) -> CanaryUsageJournalEvent:
        """验证并追加一个快照，在返回前 flush 与 fsync。"""
        if not self._opened:
            detail = "Canary 用量日志尚未打开"
            raise LiveCanaryUsageStoreError(detail)
        if snapshot.trial_id in self._terminal_trials:
            detail = f"Canary Trial 已存在终态: {snapshot.trial_id}"
            raise LiveCanaryUsageStoreError(detail)
        event = CanaryUsageJournalEvent(
            sequence=len(self._events) + 1,
            recorded_at=datetime.now(UTC),
            event_type=snapshot.event_type,
            protocol_id=self._protocol_id,
            config_id=self._config.id,
            config_sha256=self._config_sha256,
            trial_id=snapshot.trial_id,
            condition_id=snapshot.condition_id,
            session_index=snapshot.session_index,
            agent_step=snapshot.agent_step,
            provider=snapshot.provider,
            model_id=snapshot.model_id,
            model_revision=snapshot.model_revision,
            api_call_count=snapshot.api_call_count,
            response_count=snapshot.response_count,
            total_reserved_usd=snapshot.total_reserved_usd,
            run_reserved_usd=snapshot.run_reserved_usd,
            response_token_usage=snapshot.response_token_usage,
            response_estimated_cost_usd=snapshot.response_estimated_cost_usd,
            actual_usage_status=usage_status(
                snapshot.api_call_count,
                snapshot.response_count,
            ),
            observed_token_usage=snapshot.observed_token_usage,
            observed_estimated_cost_usd=snapshot.observed_estimated_cost_usd,
            completed_session_indices=snapshot.completed_session_indices,
            terminal_status=snapshot.terminal_status,
            stop_detail=snapshot.stop_detail,
        )
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(event.model_dump_json())
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            detail = "Canary 用量日志追加失败"
            raise LiveCanaryUsageStoreError(detail) from error
        self._events.append(event)
        if snapshot.event_type == "terminal":
            self._terminal_trials.add(snapshot.trial_id)
        return event


def load_canary_usage_events(path: Path) -> tuple[CanaryUsageJournalEvent, ...]:
    """严格读取事件，并拒绝 sequence 或终态顺序损坏。"""
    try:
        lines = tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)
    except OSError as error:
        detail = f"无法读取 Canary 用量日志: {path}"
        raise LiveCanaryUsageStoreError(detail) from error
    events = tuple(CanaryUsageJournalEvent.model_validate_json(line) for line in lines)
    if tuple(item.sequence for item in events) != tuple(range(1, len(events) + 1)):
        detail = "Canary 用量日志 sequence 不连续"
        raise LiveCanaryUsageStoreError(detail)
    terminal_trials: set[str] = set()
    identities: set[tuple[str, str, str]] = set()
    for event in events:
        identities.add((event.protocol_id, event.config_id, event.config_sha256))
        if event.trial_id in terminal_trials:
            detail = "Canary Trial 终态后仍有事件"
            raise LiveCanaryUsageStoreError(detail)
        if event.event_type == "terminal":
            terminal_trials.add(event.trial_id)
    if len(identities) > 1:
        detail = "Canary 用量日志合同身份不一致"
        raise LiveCanaryUsageStoreError(detail)
    return events


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = (
    "ActualUsageStatus",
    "CanaryUsageJournalEvent",
    "LiveCanaryMetadataDriftError",
    "LiveCanaryUsageJournal",
    "LiveCanaryUsageStoreError",
    "LiveTrialTerminalStatus",
    "load_canary_usage_events",
)
