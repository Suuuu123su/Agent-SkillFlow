"""T10 公共 checkpoint 与隔离恢复分支的执行器。"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from skillflow.adapters.benchmark_controller import BenchmarkController
from skillflow.benchmark.harness_factory import HarnessFactorySetup, create_scenario_harness
from skillflow.benchmark.manifests import ManifestBinding
from skillflow.benchmark.replay_models import ReplayBranchResult, ReplaySourceState
from skillflow.benchmark.run_workspace import stage_assets
from skillflow.benchmark.runner import ScenarioHarnessFactory
from skillflow.benchmark.scenario_execution import ScenarioExecutor, ScenarioExecutorSetup
from skillflow.benchmark.scripted_backend import FixtureScript
from skillflow.instrumentation.artifact_intervention import ArtifactInterventionMode
from skillflow.models.enums import Decision
from skillflow.models.scenario import Scenario
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.sqlite_store import SqliteEventStore


@dataclass(frozen=True, slots=True)
class ReplayRuntimeConfig:
    """所有配对分支共享的不可变 Runtime 配置。"""

    scenario: Scenario
    scripts: Mapping[str, FixtureScript]
    decisions: Mapping[str, Decision]
    manifests: tuple[ManifestBinding, ...]
    seed: str
    harness_factory: ScenarioHarnessFactory | None = None


@dataclass(frozen=True, slots=True)
class ReplaySourceSetup:
    """公共 checkpoint 分支的执行配置。"""

    runtime: ReplayRuntimeConfig
    run_id: str
    run_root: Path
    target_alias: str


@dataclass(frozen=True, slots=True)
class ReplayBranchSetup:
    """一个恢复后干预分支的执行配置。"""

    runtime: ReplayRuntimeConfig
    run_id: str
    run_root: Path
    target_alias: str
    source: ReplaySourceState
    mode: ArtifactInterventionMode


@dataclass(frozen=True, slots=True)
class ReplayBranchResources:
    """一次 Run 装配 Harness 所需的分支资源。"""

    runtime: ReplayRuntimeConfig
    run_id: str
    workspace: Path
    store: SqliteEventStore
    blobs: RunBlobStore


def capture_replay_source(setup: ReplaySourceSetup) -> ReplaySourceState:
    """执行到目标 alias 后冻结完整 Harness 与编排器状态。"""
    workspace, database = _create_run_root(setup.run_root)
    stage_assets(setup.runtime.scenario, workspace)
    with (
        SqliteEventStore(database) as store,
        RunBlobStore(setup.run_root, setup.run_id) as blobs,
    ):
        factory = setup.runtime.harness_factory or create_scenario_harness
        harness = factory(
            _harness_setup(
                ReplayBranchResources(setup.runtime, setup.run_id, workspace, store, blobs)
            )
        )
        executor = ScenarioExecutor(
            ScenarioExecutorSetup(scenario=setup.runtime.scenario, harness=harness)
        )
        execution = executor.run_until_alias(setup.target_alias)
        checkpoint = harness.checkpoint()
        source_artifact_id = executor.artifact_id(setup.target_alias)
    return ReplaySourceState(checkpoint, execution, source_artifact_id)


def run_replay_branch(setup: ReplayBranchSetup) -> ReplayBranchResult:
    """从公共 checkpoint 恢复、派生干预 Artifact 并执行剩余后缀。"""
    workspace, database = _create_run_root(setup.run_root)
    with (
        SqliteEventStore(database) as store,
        RunBlobStore(setup.run_root, setup.run_id) as blobs,
    ):
        factory = setup.runtime.harness_factory or create_scenario_harness
        harness = factory(
            _harness_setup(
                ReplayBranchResources(setup.runtime, setup.run_id, workspace, store, blobs)
            )
        )
        harness.restore(setup.source.checkpoint)
        restored = harness.checkpoint()
        intervention = BenchmarkController(harness).intervene_artifact(
            setup.source.source_artifact_id,
            setup.mode,
        )
        executor = ScenarioExecutor(
            ScenarioExecutorSetup(
                scenario=setup.runtime.scenario,
                harness=harness,
                snapshot=setup.source.execution,
            )
        )
        executor.replace_alias(setup.target_alias, intervention.derived.artifact_id)
        execution = executor.run_all()
        prefix_ids = _checkpoint_effect_ids(setup.source)
        effects = tuple(
            effect
            for effect in store.iter_run_effects(setup.run_id)
            if effect.effect_id not in prefix_ids
        )
        effect_ids = frozenset(effect.effect_id for effect in effects)
        receipts = tuple(
            receipt for receipt in execution.receipts if receipt.effect_id in effect_ids
        )
        decisions = tuple(
            decision
            for event in store.iter_run_events(setup.run_id)
            if event.decision_id is not None
            for decision in (store.get_decision(event.decision_id),)
            if decision is not None
        )
    return ReplayBranchResult(
        run_id=setup.run_id,
        restore_state_hash=restored.state_hash,
        prefix_hash=restored.prefix_hash,
        intervention=intervention,
        pre_intervention_skill_state=restored.skill_state,
        effects=effects,
        receipts=receipts,
        decisions=decisions,
    )


def _create_run_root(run_root: Path) -> tuple[Path, Path]:
    run_root.mkdir(parents=True, exist_ok=False)
    workspace = run_root / "workspace"
    workspace.mkdir()
    return workspace, run_root / "state.sqlite"


def _harness_setup(resources: ReplayBranchResources) -> HarnessFactorySetup:
    runtime = resources.runtime
    return HarnessFactorySetup(
        scenario=runtime.scenario,
        run_id=resources.run_id,
        workspace=resources.workspace,
        event_store=resources.store,
        blob_store=resources.blobs,
        scripts=runtime.scripts,
        decisions=runtime.decisions,
        manifests=runtime.manifests,
        seed=runtime.seed,
    )


def _checkpoint_effect_ids(source: ReplaySourceState) -> frozenset[str]:
    return frozenset(
        envelope.effect.effect_id
        for envelope in source.checkpoint.store.envelopes
        if envelope.effect is not None
    )
