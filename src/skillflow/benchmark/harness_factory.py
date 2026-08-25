"""ScenarioRunner 与 ReplayRunner 共享的 Harness 装配。"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from skillflow.adapters.mock_harness import MockHarnessAdapter, MockHarnessConfig
from skillflow.benchmark.manifests import ManifestBinding
from skillflow.benchmark.scripted_backend import FixtureScript, ScriptedBackend
from skillflow.models.enums import Decision
from skillflow.models.scenario import Scenario
from skillflow.policy.runtime import RuntimePolicySetup, StoredPolicyDecisionProvider
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import RuntimeDependencies
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.event_store import EventStore


@dataclass(frozen=True, slots=True)
class HarnessFactorySetup:
    """确定性 Harness 的全部固定配置与分支资源。"""

    scenario: Scenario
    run_id: str
    workspace: Path
    event_store: EventStore
    blob_store: RunBlobStore
    scripts: Mapping[str, FixtureScript]
    decisions: Mapping[str, Decision]
    manifests: tuple[ManifestBinding, ...]
    seed: str


def create_scenario_harness(setup: HarnessFactorySetup) -> MockHarnessAdapter:
    """为一个全新 Run 创建隔离 Harness 与正式策略适配器。"""
    scenario = setup.scenario
    dependencies = RuntimeDependencies(
        event_store=setup.event_store,
        blob_store=setup.blob_store,
        clock=VirtualClock(scenario.clock.start),
        id_factory=DeterministicIdFactory(setup.seed),
        provenance_mode=scenario.harness.provenance_mode,
    )
    policy = StoredPolicyDecisionProvider(
        setup.event_store,
        RuntimePolicySetup(
            run_id=setup.run_id,
            manifests={binding.skill_id: binding.manifest for binding in setup.manifests},
            structural_decisions=setup.decisions,
            enforcement_mode=scenario.execution.mode,
            auto_approve_tools=scenario.harness.auto_approve_tools,
            implicit_text_authorization=scenario.harness.implicit_text_authorization,
        ),
    )
    return MockHarnessAdapter(
        MockHarnessConfig(
            run_id=setup.run_id,
            task_id=scenario.task.id,
            workspace_root=setup.workspace,
            dependencies=dependencies,
            initial_grants=scenario.grants,
        ),
        ScriptedBackend(setup.scripts),
        policy,
    )
