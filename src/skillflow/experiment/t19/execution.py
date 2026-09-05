"""T19 单链执行与脱敏事实导出；不隐式扩大调度或重采模型行为。"""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal

from skillflow.analysis.facts import RunReportMetadata
from skillflow.benchmark.runner import ScenarioRunLayout, ScenarioRunner, ScenarioRunRequest
from skillflow.defense.rx import Component, TaskConstraints, TreatmentName
from skillflow.defense.rx_provider import RxTrace
from skillflow.experiment.t17.reference_backend import ReferenceModelClient
from skillflow.experiment.t17.v2.api_models import AccountingClient
from skillflow.experiment.t17.v2.claim_setup import claim_specs
from skillflow.experiment.t17.v2.portable import capture_core
from skillflow.experiment.t17.v2.portable_models import PortableCore
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t17.v2.runtime_models import DecisionFact, ExecutionIssue
from skillflow.experiment.t18.catalog_models import LocalSkill
from skillflow.experiment.t19.boundaries import BoundaryIssue
from skillflow.experiment.t19.recovery import LimitFact, RecoveryFact
from skillflow.experiment.t19.runtime import RxHarnessFactory
from skillflow.experiment.t19.tasks import trusted_task
from skillflow.models.base import StrictModel


class CoreRecord(StrictModel):
    """原始结构化事实用于独立复算；分组身份不能进入Router。"""

    unit_id: str
    domain: Literal["scripted", "fake_reference", "live_reference"]
    group: TreatmentName
    status: Literal["completed"] = "completed"
    data: PortableCore
    traces: tuple[RxTrace, ...]
    recoveries: tuple[RecoveryFact, ...]
    decisions: tuple[DecisionFact, ...]
    issues: tuple[ExecutionIssue, ...]
    usage: UnitUsage
    latency_ms: float
    limits: tuple[LimitFact, ...] = ()
    boundary_issues: tuple[BoundaryIssue, ...] = ()
    task_constraints: TaskConstraints | None = None


@dataclass(frozen=True, slots=True)
class ExecutionSetup:
    """已登记一个单元；调用者在进入前负责预算与阶段冻结。"""

    root: Path
    output: Path
    unit_id: str
    domain: Literal["scripted", "fake_reference", "live_reference"]
    group: TreatmentName
    fixed: tuple[Component, ...] = ()
    bridge: bool = True


def execute(
    setup: ExecutionSetup, skill: LocalSkill, client: ReferenceModelClient | None
) -> tuple[CoreRecord, RxHarnessFactory]:
    """保留现场检查点供随后事后补证，正式结果先独占落盘。"""
    started = perf_counter()
    if (client is None) != (setup.domain == "scripted"):
        raise ValueError("t19_execution_domain_client_mismatch")
    factory = RxHarnessFactory(
        trusted_task(skill.base_id),
        setup.group,
        client,
        setup.fixed,
        bridge_data_only=not setup.bridge,
    )
    # Cross-skill data remains connected; RxHarness closes only the control field.
    scenario = skill.scenario.model_copy(
        update={
            "harness": skill.scenario.harness.model_copy(update={"shared_context": True}),
        }
    )
    metadata = RunReportMetadata(
        experiment_id="t19-rx-v1",
        backend="reference_harness",
        variant=setup.unit_id,
        shared_context=setup.bridge,
        auto_approve_tools=scenario.harness.auto_approve_tools,
        implicit_text_authorization=scenario.harness.implicit_text_authorization,
        persistent_memory=scenario.harness.persistent_memory,
        provenance_mode=scenario.harness.provenance_mode,
    )
    directory = setup.output / setup.unit_id
    result = ScenarioRunner(
        skill.bundle.scripts,
        skill.bundle.decisions,
        factory,
        execution_policy=factory.execution_policy,
    ).run_configured(
        ScenarioRunRequest(
            setup.root / skill.scenario_path,
            scenario,
            setup.unit_id,
            setup.unit_id,
            ScenarioRunLayout(
                directory,
                directory,
                directory / "state.sqlite",
                directory / "workspace",
                directory / "graph.json",
                directory / "risk.json",
            ),
            metadata,
        )
    )
    capture = factory.captures[setup.unit_id]
    record = CoreRecord(
        unit_id=setup.unit_id,
        task_constraints=factory.task,
        domain=setup.domain,
        group=setup.group,
        data=capture_core(
            result, scenario, skill.task_contract, metadata, claim_specs(scenario, skill.bundle)
        ),
        traces=tuple(factory.providers[setup.unit_id].traces),
        recoveries=tuple(factory.backends[setup.unit_id].recoveries)
        if setup.unit_id in factory.backends
        else (),
        limits=tuple(factory.backends[setup.unit_id].limits)
        if setup.unit_id in factory.backends
        else (),
        boundary_issues=tuple(factory.boundary_issues[setup.unit_id]),
        decisions=tuple(capture.decisions),
        issues=tuple(capture.issues),
        usage=client.unit_usage() if isinstance(client, AccountingClient) else UnitUsage(),
        latency_ms=(perf_counter() - started) * 1000,
    )
    return record, factory
