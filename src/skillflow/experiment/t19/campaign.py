"""T19 固定矩阵串行执行；已完成核心与补证不重复调用。"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from skillflow.defense.rx import Component
from skillflow.experiment.t17.reference_backend import ReferenceModelClient
from skillflow.experiment.t17.v2.replay_proof import source_facts
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t17.v2.runtime_models import RunCapture
from skillflow.experiment.t19.execution import CoreRecord, ExecutionSetup, execute
from skillflow.experiment.t19.live import T19LiveClient
from skillflow.experiment.t19.matrix import Trial
from skillflow.experiment.t19.persistence import PrivateReplaySource, save_source, write_record
from skillflow.experiment.t19.replay import ReplayRecord, ReplaySetup, run_pair
from skillflow.experiment.t19.runtime import RxHarnessFactory
from skillflow.experiment.t19.tasks import task_variant, trusted_task
from skillflow.models.base import StrictModel
from skillflow.models.enums import EventType


class CampaignPlan(StrictModel):
    """实际执行身份绑定，正式组或任务不能在恢复时改变。"""

    domain: Literal["fake_reference", "live_reference"]
    fixed: tuple[Component, ...]
    trials: tuple[Trial, ...]
    audit_aliases: dict[str, tuple[str, ...]]


class Progress(StrictModel):
    """仅汇报计数，不输出模型正文和凭据。"""

    completed_core: int
    scheduled_core: int
    completed_audit: int
    scheduled_audit: int
    current_id: str


@dataclass(frozen=True, slots=True)
class CampaignSetup:
    """Live 客户端须在外层完成冻结检查和累计预算初始化。"""

    root: Path
    output: Path
    plan: CampaignPlan
    client: ReferenceModelClient
    progress: Callable[[Progress], None]


def run_campaign(setup: CampaignSetup) -> None:
    """只补缺少终态且没有不明现场的单元，不择优重采失败行为。"""
    plan_path = setup.output / "execution-plan.json"
    if plan_path.exists():
        saved = CampaignPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
        if saved != setup.plan:
            raise ValueError("t19_resume_plan_drift")
    else:
        write_record(plan_path, setup.plan)
    if (setup.plan.domain == "live_reference") != isinstance(setup.client, T19LiveClient):
        raise ValueError("t19_campaign_domain_mismatch")
    audited = 0
    for completed, trial in enumerate(setup.plan.trials, start=1):
        core, factory = _core(setup, trial)
        for alias in setup.plan.audit_aliases.get(trial.trial_id, ()):
            _audit(setup, trial, core, factory, alias)
            audited += 1
        setup.progress(
            Progress(
                completed_core=completed,
                scheduled_core=len(setup.plan.trials),
                completed_audit=audited,
                scheduled_audit=sum(len(a) for a in setup.plan.audit_aliases.values()),
                current_id=trial.trial_id,
            )
        )


def _core(setup: CampaignSetup, trial: Trial) -> tuple[CoreRecord, RxHarnessFactory]:
    terminal = setup.output / "core" / (trial.trial_id + ".json")
    private = setup.output / "checkpoints" / trial.trial_id
    skill = task_variant(setup.root, trial.mechanism, trial.role, trial.template)
    if terminal.exists():
        core = CoreRecord.model_validate_json(terminal.read_text(encoding="utf-8"))
        if (
            core.unit_id != trial.trial_id
            or core.group != trial.group
            or core.domain != setup.plan.domain
        ):
            raise ValueError("t19_resume_core_binding")
        factory = RxHarnessFactory(
            trusted_task(trial.mechanism),
            trial.group,
            setup.client,
            setup.plan.fixed,
            bridge_data_only=not trial.bridge,
        )
        capture = RunCapture(
            trial.trial_id, decisions=list(core.decisions), issues=list(core.issues)
        )
        for path in sorted(private.glob("*.json")):
            saved_source = PrivateReplaySource.model_validate_json(path.read_text(encoding="utf-8"))
            capture.checkpoints[path.stem] = saved_source.source()
            factory.replay_prefix_steps[path.stem] = saved_source.prefix_steps
        factory.captures[trial.trial_id] = capture
        expected = {c.target.alias for c in skill.scenario.counterfactuals}
        produced = expected.intersection(core.data.artifact_ids_by_alias)
        if produced != set(capture.checkpoints):
            raise ValueError("t19_resume_checkpoint_missing")
        return core, factory
    raw = setup.output / "raw"
    if (raw / trial.trial_id).exists():
        raise ValueError("t19_unclosed_core_requires_local_reconciliation")
    if isinstance(setup.client, T19LiveClient):
        setup.client.begin_unit(trial.trial_id)
    core, factory = execute(
        ExecutionSetup(
            setup.root,
            raw,
            trial.trial_id,
            setup.plan.domain,
            trial.group,
            setup.plan.fixed,
            trial.bridge,
        ),
        skill,
        setup.client,
    )
    for alias, source in factory.captures[trial.trial_id].checkpoints.items():
        calls = frozenset(
            e.call_id
            for e in source_facts(source).events
            if e.event_type is EventType.SKILL_INVOKE and e.call_id is not None
        )
        prefix = (
            setup.client.prefix_steps(trial.trial_id, calls)
            if isinstance(setup.client, T19LiveClient)
            else sum(d.call_id in calls for d in core.decisions)
        )
        factory.replay_prefix_steps[alias] = prefix
        save_source(private / (alias + ".json"), source, prefix_steps=prefix)
    write_record(terminal, core)
    return core, factory


def _audit(
    setup: CampaignSetup, trial: Trial, core: CoreRecord, factory: RxHarnessFactory, alias: str
) -> None:
    terminal = setup.output / "audits" / trial.trial_id / (alias + ".json")
    if terminal.exists():
        record = ReplayRecord.model_validate_json(terminal.read_text(encoding="utf-8"))
        if record.source_unit_id != trial.trial_id or record.target_alias != alias:
            raise ValueError("t19_resume_audit_binding")
        return
    client = setup.client
    replay_setup = ReplaySetup(
        setup.root,
        setup.output / "replay-raw",
        client,
        client.begin_replay if isinstance(client, T19LiveClient) else lambda _n, _p: None,
        client.unit_usage if isinstance(client, T19LiveClient) else UnitUsage,
    )
    record = run_pair(
        replay_setup,
        core,
        task_variant(setup.root, trial.mechanism, trial.role, trial.template),
        factory,
        alias,
    )
    write_record(terminal, record)
