"""逐调用日志的状态顺序：哈希有效不等于响应和结算绑定有效。"""

from dataclasses import dataclass, field

from skillflow.experiment.t17.v2.api_models import ApiUsageEvent


@dataclass(slots=True)
class JournalOrder:
    """允许中断末尾没有响应，禁止重复尝试、错绑或提前结算。"""

    unit_id: str | None = None
    phase_sha256: str | None = None
    units: set[str] = field(default_factory=set)
    attempts: dict[int, ApiUsageEvent] = field(default_factory=dict)
    outcomes: dict[int, ApiUsageEvent] = field(default_factory=dict)
    settled: set[int] = field(default_factory=set)

    def accept(self, event: ApiUsageEvent) -> None:
        """日志只能按真实运行的单元、尝试、响应和结算推进。"""
        if event.event_type == "unit_start":
            self._unit(event)
            return
        if event.unit_id != self.unit_id or event.phase_contract_sha256 != self.phase_sha256:
            raise ValueError("v2_usage_active_unit_binding")
        if event.event_type == "attempt":
            self._attempt(event)
            return
        attempt = self.attempts.get(event.attempt_index)
        if attempt is None or attempt.call != event.call or attempt.unit_id != event.unit_id:
            raise ValueError("v2_usage_outcome_attempt_binding")
        if event.event_type in {"response", "http_error", "transport_failure"}:
            if event.attempt_index in self.outcomes:
                raise ValueError("v2_usage_duplicate_outcome")
            self.outcomes[event.attempt_index] = event
        elif event.event_type == "settlement":
            self._settlement(event)
        elif event.attempt_index not in self.settled:
            raise ValueError("v2_usage_behavior_before_settlement")

    def _closed(self) -> bool:
        if not self.attempts:
            return True
        index = max(self.attempts)
        outcome = self.outcomes.get(index)
        return outcome is not None and (outcome.event_type != "response" or index in self.settled)

    def _unit(self, event: ApiUsageEvent) -> None:
        if event.unit_id in self.units or event.call is not None or not self._closed():
            raise ValueError("v2_usage_unit_start_order")
        self.units.add(event.unit_id)
        self.unit_id = event.unit_id
        self.phase_sha256 = event.phase_contract_sha256

    def _attempt(self, event: ApiUsageEvent) -> None:
        if event.attempt_index != len(self.attempts) + 1 or not self._closed():
            raise ValueError("v2_usage_attempt_order")
        if any(
            previous.call == event.call and previous.event_type == "response"
            for previous in self.outcomes.values()
        ):
            raise ValueError("v2_usage_model_result_resampled")
        self.attempts[event.attempt_index] = event

    def _settlement(self, event: ApiUsageEvent) -> None:
        outcome = self.outcomes.get(event.attempt_index)
        if (
            outcome is None
            or outcome.event_type != "response"
            or event.attempt_index in self.settled
        ):
            raise ValueError("v2_usage_settlement_order")
        self.settled.add(event.attempt_index)
