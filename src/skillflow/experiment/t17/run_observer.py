"""为每个 T17 Matrix Run 写出强类型 Hook 与 Task 证据。"""

from collections.abc import Mapping
from pathlib import Path

from skillflow.experiment.io import write_json_model
from skillflow.experiment.matrix_support import ExecutedVariant
from skillflow.experiment.t17.contracts import HookName
from skillflow.experiment.t17.observations import (
    ReferenceObservationRequest,
    ReferenceObservationSnapshot,
    build_reference_observations,
)
from skillflow.experiment.t17.scenario_registry import (
    T17ScenarioMeasurement,
    T17ScenarioMeasurementRegistry,
    expand_variant_measurements,
)
from skillflow.experiment.t17.task_evidence import build_task_success_evidence
from skillflow.store.sqlite_store import SqliteEventStore


class T17RunObservationWriter:
    """保存每个 Run 的可信证据；内部列表用于阶段聚合。"""

    def __init__(
        self,
        registry: T17ScenarioMeasurementRegistry,
        project_root: Path = Path(),
        variant_specifications: Mapping[
            str,
            T17ScenarioMeasurement,
        ]
        | None = None,
    ) -> None:
        """机械展开 variant→场景合同并初始化累计结果。"""
        specifications = {
            item.variant: item.scenario
            for item in expand_variant_measurements(project_root, registry)
        }
        if variant_specifications is not None:
            specifications.update(variant_specifications)
        self._specifications = specifications
        self._snapshots: list[ReferenceObservationSnapshot] = []

    @property
    def snapshots(self) -> tuple[ReferenceObservationSnapshot, ...]:
        """返回已完成 Run 的不可变快照序列。"""
        return tuple(self._snapshots)

    def __call__(self, item: ExecutedVariant) -> None:
        """从刚完成的 Run 事实构造并不可覆盖写出 Observation。"""
        specification = self._specifications[item.variant.variant]
        with SqliteEventStore(item.result.database_path) as store:
            task_evidence = build_task_success_evidence(
                item.result,
                specification,
                store,
            )
            required_hooks = _run_required_hooks(specification)
            snapshot = build_reference_observations(
                ReferenceObservationRequest(
                    store=store,
                    run_id=item.result.run_id,
                    receipts=item.result.receipts,
                    task_success_evidence=task_evidence,
                    required_hooks=required_hooks,
                )
            )
        write_json_model(
            item.result.risk_report_path.parent / "t17-observations.json",
            snapshot,
        )
        self._snapshots.append(snapshot)


def _run_required_hooks(
    specification: T17ScenarioMeasurement,
) -> frozenset[HookName]:
    required = set(specification.required_hooks)
    required.discard(HookName.INFLUENCE)
    return frozenset(required)
