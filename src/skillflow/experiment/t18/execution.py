"""一条已登记核心任务的真实本地执行、检查点和不可变终态写入。"""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from skillflow.analysis.facts import RunReportMetadata
from skillflow.benchmark.runner import ScenarioRunLayout, ScenarioRunner, ScenarioRunRequest
from skillflow.experiment.t17.v2.portable import capture_core
from skillflow.experiment.t18.catalog_models import LocalSkill
from skillflow.experiment.t18.controls import configured_scenario
from skillflow.experiment.t18.matrix import CoreCell, Domain
from skillflow.experiment.t18.replay import ReplayBudget, ReplayCoordinator
from skillflow.experiment.t18.run_models import LocalCore
from skillflow.experiment.t18.runtime import LocalHarnessFactory


@dataclass(frozen=True, slots=True)
class CoreContext:
    """同阶段共享位置、域和硬预算，不含评分标签。"""

    project: Path
    output: Path
    domain: Domain
    phase_sha256: str
    budget: ReplayBudget


def execute_core(context: CoreContext, skill: LocalSkill, cell: CoreCell, number: int) -> LocalCore:
    """阶段仅调用登记的一条任务；没有隐藏重采样或附加模型请求。"""
    started = perf_counter()
    project, output, domain = context.project, context.output, context.domain
    phase_sha256, budget = context.phase_sha256, context.budget
    run_id = "t18-" + domain + "-" + cell.trial_id
    directory = output / "core" / f"c{number:03d}"
    scenario = configured_scenario(skill, cell)
    factory = LocalHarnessFactory(skill, cell.mode, domain)
    replay = ReplayCoordinator(project, output, skill, cell, scenario, factory, run_id, budget)
    factory.replay = replay.online
    metadata = RunReportMetadata(
        backend="reference_harness",
        experiment_id="t18-local-hiaa-v1",
        variant=cell.trial_id,
        shared_context=cell.bridge_enabled,
        enforcement_mode=scenario.execution.mode,
    )
    result = ScenarioRunner(
        skill.bundle.scripts,
        skill.bundle.decisions,
        factory,
        execution_policy=factory.execution_policy,
    ).run_configured(
        ScenarioRunRequest(
            project / skill.scenario_path,
            scenario,
            run_id,
            cell.seed,
            ScenarioRunLayout(
                directory,
                directory,
                directory / "state.sqlite",
                directory / "workspace",
                directory / "security-graph.json",
                directory / "risk-report.json",
            ),
            metadata,
        )
    )
    data = capture_core(result, scenario, skill.task_contract, metadata)
    if (
        cell.role == "attack"
        and cell.mode == "monitor"
        and cell.bridge_enabled
        and data.proof.task.risk_effect_ids
    ):
        for counterfactual in scenario.counterfactuals:
            if counterfactual.target.alias in factory.captures[run_id].checkpoints:
                replay.run_pair(counterfactual.target.alias, online=False)
    capture = factory.captures[run_id]
    record = LocalCore(
        phase_contract_sha256=phase_sha256,
        domain=domain,
        cell=cell,
        run_id=run_id,
        status="completed",
        data=data,
        traces=tuple(factory.providers[run_id].traces),
        decisions=tuple(capture.decisions),
        issues=tuple(capture.issues),
        replay_pair_ids=tuple(p.pair_id for p in replay.records),
        latency_ms=(perf_counter() - started) * 1000,
    )
    terminal = output / "terminals" / f"c{number:03d}.json"
    terminal.parent.mkdir(parents=True, exist_ok=True)
    with terminal.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(record.model_dump_json(indent=2) + "\n")
    return record
