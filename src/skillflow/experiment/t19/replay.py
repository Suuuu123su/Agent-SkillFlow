"""T19 事后同源重放：identity、control中和、同视图波动。"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from skillflow.benchmark.manifests import load_manifests
from skillflow.benchmark.replay_analysis import ReplayAnalysisSetup, analyze_replay_pair
from skillflow.benchmark.replay_branch import (
    ReplayBranchSetup,
    ReplayRuntimeConfig,
    run_replay_branch,
)
from skillflow.benchmark.replay_fingerprint import ReplayFingerprintSetup, build_control_evidence
from skillflow.experiment.t17.minimal.raw_validation import restore_run_receipts
from skillflow.experiment.t17.reference_backend import ReferenceModelClient
from skillflow.experiment.t17.v2.portable import capture_run
from skillflow.experiment.t17.v2.portable_models import PortableRun
from skillflow.experiment.t17.v2.replay_proof import build_replay_proof, source_facts
from skillflow.experiment.t17.v2.run_models import ReplayProof, UnitUsage
from skillflow.experiment.t18.catalog_models import LocalSkill
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.experiment.t19.live import T19LiveClient
from skillflow.experiment.t19.neutralization import neutralize_control
from skillflow.experiment.t19.persistence import SavedBranch, write_record
from skillflow.experiment.t19.runtime import RxHarnessFactory
from skillflow.instrumentation.artifact_intervention import ArtifactInterventionMode
from skillflow.models.base import StrictModel
from skillflow.models.enums import EventType
from skillflow.store.sqlite_store import SqliteEventStore

MAX_CHAIN_STEPS = 16


class ReplayRecord(StrictModel):
    """无适用目标和有证据差值分别记录；same_view不计新增研究样本。"""

    pair_id: str
    source_unit_id: str
    target_alias: str
    status: Literal["completed", "not_applicable"]
    reason: str
    proof: ReplayProof | None = None
    same_view: PortableRun | None = None
    absent_source: PortableRun | None = None
    source_prefix_steps: int
    branch_usage: tuple[UnitUsage, ...] = ()
    branch_details: tuple[SavedBranch, ...] = ()


@dataclass(frozen=True, slots=True)
class ReplaySetup:
    """只有事后实验器持有client，Router不持有重放入口。"""

    root: Path
    output: Path
    client: ReferenceModelClient | None
    begin_branch: Callable[[str, int], None]
    usage: Callable[[], UnitUsage]


def run_pair(
    setup: ReplaySetup,
    core: CoreRecord,
    skill: LocalSkill,
    original_factory: RxHarnessFactory,
    alias: str,
) -> ReplayRecord:
    """在已完成核心的实际checkpoint上运行，原核心不会重采。"""
    pair_id = core.unit_id + ":audit:" + alias
    capture = original_factory.captures[core.unit_id]
    source = capture.checkpoints.get(alias)
    if source is None:
        return ReplayRecord(
            pair_id=pair_id,
            source_unit_id=core.unit_id,
            target_alias=alias,
            status="not_applicable",
            reason="target_not_produced_in_closed_core",
            absent_source=core.data.facts,
            source_prefix_steps=0,
        )
    facts = source_facts(source)
    target = next(
        a
        for a in source.checkpoint.store.artifacts
        if a.artifact.artifact_id == source.source_artifact_id
    )
    try:
        neutralize_control(target.content)
    except (ValueError, TypeError):
        retained = tuple(
            SavedBranch.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted((setup.output / core.unit_id / alias).glob("*/branch-result.json"))
        )
        return ReplayRecord(
            pair_id=pair_id,
            source_unit_id=core.unit_id,
            target_alias=alias,
            status="not_applicable",
            reason="source_generation_outside_frozen_control_envelope",
            absent_source=core.data.facts,
            source_prefix_steps=original_factory.replay_prefix_steps.get(alias, 0),
            branch_usage=tuple(b.usage for b in retained),
            branch_details=retained,
        )
    calls = {e.call_id for e in facts.events if e.event_type is EventType.SKILL_INVOKE}
    prefix_steps = (
        setup.client.prefix_steps(core.unit_id, frozenset(c for c in calls if c is not None))
        if isinstance(setup.client, T19LiveClient)
        else sum(d.call_id in calls for d in capture.decisions)
    )
    prefix_steps = original_factory.replay_prefix_steps.get(alias, prefix_steps)
    if prefix_steps >= MAX_CHAIN_STEPS:
        raise ValueError("t19_replay_no_remaining_step_budget")
    factory = RxHarnessFactory(
        original_factory.task,
        core.group,
        setup.client,
        original_factory.fixed,
        bridge_data_only=original_factory.bridge_data_only,
    )
    scenario = skill.scenario.model_copy(
        update={
            "harness": skill.scenario.harness.model_copy(update={"shared_context": True}),
        }
    )
    manifests = load_manifests(setup.root / skill.scenario_path, scenario)
    runtime = ReplayRuntimeConfig(
        scenario,
        skill.bundle.scripts,
        skill.bundle.decisions,
        manifests,
        core.unit_id,
        factory,
        factory.execution_policy.factory,
    )
    branches = []
    usages = []
    paths = []
    details = []
    for name, mode in (
        ("identity", ArtifactInterventionMode.IDENTITY),
        ("neutral", ArtifactInterventionMode.NEUTRAL),
        ("same_view", ArtifactInterventionMode.IDENTITY),
    ):
        branch_id = pair_id + ":" + name
        path = setup.output / core.unit_id / alias / name
        terminal = path / "branch-result.json"
        if terminal.exists():
            saved = SavedBranch.model_validate_json(terminal.read_text(encoding="utf-8"))
            if saved.result.run_id != branch_id:
                raise ValueError("t19_replay_resume_branch_binding")
        else:
            if (path / "state.sqlite").exists():
                raise ValueError("t19_unclosed_branch_requires_local_reconciliation")
            setup.begin_branch(branch_id, prefix_steps)
            result = run_replay_branch(
                ReplayBranchSetup(
                    runtime,
                    branch_id,
                    path,
                    alias,
                    source,
                    mode,
                )
            )
            capture_branch = factory.captures[branch_id]
            backend = factory.backends.get(branch_id)
            saved = SavedBranch(
                result=result,
                usage=setup.usage(),
                decisions=tuple(capture_branch.decisions),
                issues=tuple(capture_branch.issues),
                recoveries=tuple(backend.recoveries) if backend else (),
                limits=tuple(backend.limits) if backend else (),
                traces=tuple(factory.providers[branch_id].traces),
                boundary_issues=tuple(factory.boundary_issues[branch_id]),
            )
            write_record(terminal, saved)
        details.append(saved)
        branches.append(saved.result)
        usages.append(saved.usage)
        paths.append(path)
    counterfactual = next(c for c in scenario.counterfactuals if c.target.alias == alias)
    selector = next(s for s in scenario.effect_selectors if s.alias == counterfactual.observe.alias)
    controls = build_control_evidence(
        ReplayFingerprintSetup(
            scenario,
            skill.bundle.scripts,
            skill.bundle.decisions,
            manifests,
            core.unit_id,
            source.checkpoint,
        )
    )
    analyzed = analyze_replay_pair(
        ReplayAnalysisSetup(
            pair_id,
            alias,
            source,
            branches[0],
            branches[1],
            selector,
            controls,
            source_run_id=core.unit_id,
        )
    )
    portable = tuple(
        _branch(path, branch.run_id) for path, branch in zip(paths, branches, strict=True)
    )
    proof = build_replay_proof(facts, portable[0], portable[1], selector, analyzed.manifest)
    return ReplayRecord(
        pair_id=pair_id,
        source_unit_id=core.unit_id,
        target_alias=alias,
        status="completed",
        reason="same_checkpoint_three_branches_not_deterministic_causality",
        proof=proof,
        same_view=portable[2],
        source_prefix_steps=prefix_steps,
        branch_usage=tuple(usages),
        branch_details=tuple(details),
    )


def _branch(path: Path, run_id: str) -> PortableRun:
    with SqliteEventStore(path / "state.sqlite") as store:
        return capture_run(store, run_id, restore_run_receipts(store, path, run_id))
