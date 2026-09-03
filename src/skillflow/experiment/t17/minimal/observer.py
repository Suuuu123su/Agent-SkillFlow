"""每个 core 完成后独立写出普通任务与六类受信 Hook。"""

import time

from skillflow.experiment.matrix_support import ExecutedVariant
from skillflow.experiment.t17.contracts import HookCapability, HookName, MeasurementStatus
from skillflow.experiment.t17.minimal.artifacts import model_digest, write_checked_json
from skillflow.experiment.t17.minimal.contracts import MinimalConfiguration
from skillflow.experiment.t17.minimal.run_models import MinimalPhaseContract, MinimalRunRecord
from skillflow.experiment.t17.minimal.runtime import MinimalHarnessFactory
from skillflow.experiment.t17.minimal.task_evidence import evaluate_normal_task
from skillflow.experiment.t17.observations import (
    ReferenceObservationRequest,
    build_reference_observations,
)
from skillflow.models.enums import EventType
from skillflow.store.sqlite_store import SqliteEventStore

_NANOSECONDS_PER_MILLISECOND = 1_000_000


class MinimalObservationWriter:
    """新的任务 Hook 使用 v2，旧 Snapshot 仅作为非任务 Runtime 投影。"""

    def __init__(
        self,
        configuration: MinimalConfiguration,
        phase: MinimalPhaseContract,
        factory: MinimalHarnessFactory,
    ) -> None:
        """绑定运行前已冻结的每场景任务与执行域。"""
        self._tasks = {item.scenario_id: item for item in configuration.tasks}
        self._phase = phase
        self._factory = factory
        self.records: list[MinimalRunRecord] = []

    def __call__(self, item: ExecutedVariant) -> None:
        """从 Runtime 事实生成证据，任何必需 Hook 缺失立即报错。"""
        result = item.result
        contract = self._tasks[result.scenario_id]
        telemetry = self._factory.telemetry[result.run_id]
        with SqliteEventStore(result.database_path) as store:
            task = evaluate_normal_task(result, contract, store)
            runtime = build_reference_observations(
                ReferenceObservationRequest(
                    store=store,
                    run_id=result.run_id,
                    receipts=result.receipts,
                    task_success_evidence=None,
                    required_hooks=frozenset(contract.required_hooks) - {HookName.TASK_SUCCESS},
                )
            )
            step_ids = tuple(
                event.event_id
                for event in store.iter_run_events(result.run_id)
                if event.event_type is EventType.SKILL_INVOKE
            )
        hooks = tuple(
            HookCapability(
                hook=HookName.TASK_SUCCESS,
                required=True,
                available=True,
                status=MeasurementStatus.MEASURED,
                evidence_ids=task.evidence_ids,
            )
            if hook.hook is HookName.TASK_SUCCESS
            else hook
            for hook in runtime.hooks
        )
        if any(hook.required and hook.status is not MeasurementStatus.MEASURED for hook in hooks):
            raise ValueError("minimal_required_hook_unmeasured")
        record = MinimalRunRecord(
            domain=self._phase.domain,
            run_id=result.run_id,
            variant=item.variant.variant,
            phase_contract_sha256=model_digest(self._phase),
            artifact_ids_by_alias=result.artifact_ids_by_alias,
            receipt_artifact_ids=tuple(receipt.receipt_artifact_id for receipt in result.receipts),
            runtime=runtime,
            task=task,
            hooks=hooks,
            step_event_ids=step_ids,
            decision_journal=() if telemetry.client is None else tuple(telemetry.client.records),
            harness_wall_latency_ms=(time.perf_counter_ns() - telemetry.started_ns)
            / _NANOSECONDS_PER_MILLISECOND,
        )
        root = result.risk_report_path.parent
        write_checked_json(root / "normal-task-evidence.json", task)
        write_checked_json(root / "minimal-run-record.json", record)
        self.records.append(record)
