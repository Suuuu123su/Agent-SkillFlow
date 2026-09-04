"""独立 T18 装配，复用原始事件、授权、记忆、检查点和安全工具执行链。"""

from dataclasses import dataclass, field

from skillflow.adapters.live_reference_harness import LiveReferenceHarnessAdapter
from skillflow.adapters.mock_harness import MockHarnessAdapter, MockHarnessConfig
from skillflow.benchmark.execution_policy import ScenarioExecutionPolicy
from skillflow.benchmark.harness_factory import HarnessFactorySetup
from skillflow.benchmark.scenario_execution import ScenarioExecutor, ScenarioExecutorSetup
from skillflow.benchmark.scripted_backend import ScriptedBackend
from skillflow.defense.models import DefenseId, Mechanism
from skillflow.defense.provider import (
    DefendedDecisionProvider,
    DefenseSetup,
    ReplayCallback,
    Treatment,
)
from skillflow.defense.router import DEFENSE_ORDER
from skillflow.experiment.t17.reference_backend import ReferenceRunContext
from skillflow.experiment.t17.v2.backend import V2ReferenceBackend
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t17.v2.runtime import V2ScenarioExecutor
from skillflow.experiment.t17.v2.runtime_models import RunCapture
from skillflow.experiment.t18.catalog_models import LocalSkill
from skillflow.experiment.t18.matrix import Domain, Mode
from skillflow.policy.runtime import RuntimePolicySetup, StoredPolicyDecisionProvider
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import RuntimeDependencies

FIXED: dict[Mode, tuple[DefenseId, ...]] = {
    "monitor": (),
    "universal_enforce": (),
    "task_alignment_only": ("task-alignment",),
    "tdg_only": ("tdg",),
    "drift_isolation_only": ("drift-isolation",),
    "causal_only": ("causal",),
    "all_defenses": DEFENSE_ORDER,
    "oracle_router": (),
    "evidence_router": (),
}
ORACLE: dict[Mechanism, tuple[DefenseId, ...]] = {
    "privilege": ("task-alignment", "drift-isolation"),
    "context-tool": ("tdg", "causal"),
    "memory": ("drift-isolation", "causal"),
    "authorization": ("task-alignment",),
}


@dataclass(slots=True)
class LocalHarnessFactory:
    """评分真值只能在明确的理想路由基线转换成固定组件。"""

    skill: LocalSkill
    mode: Mode
    domain: Domain
    replay: ReplayCallback | None = None
    shadow: bool = False
    captures: dict[str, RunCapture] = field(default_factory=dict)
    providers: dict[str, DefendedDecisionProvider] = field(default_factory=dict)
    bindings: dict[int, RunCapture] = field(default_factory=dict)

    @property
    def execution_policy(self) -> ScenarioExecutionPolicy:
        """只终态化未满足输入，不对被阻动作强制历史成功预期。"""
        return ScenarioExecutionPolicy(self.executor, validate_scripted_expectations=False)

    def executor(self, setup: ScenarioExecutorSetup) -> ScenarioExecutor:
        """记录真实检查点，不用重建的目标载荷代替现场状态。"""
        return V2ScenarioExecutor(setup, self.bindings[id(setup.harness)])

    def __call__(self, setup: HarnessFactorySetup) -> MockHarnessAdapter:
        """工具与基础策略保持原有接口，模型域只替换动作选择客户端。"""
        if {b.skill_id: b.manifest for b in setup.manifests} != self.skill.manifests:
            raise ValueError("t18_runtime_manifest_drift")
        capture = RunCapture(setup.run_id, capture_checkpoints=not self.shadow)
        self.captures[setup.run_id] = capture
        backend = (
            ScriptedBackend(setup.scripts)
            if self.domain == "scripted"
            else V2ReferenceBackend(
                setup.scripts,
                V2FakeClient(),
                ReferenceRunContext(setup.scenario.id, setup.scenario.task.prompt),
                capture,
                setup.event_store,
            )
        )
        scenario = setup.scenario
        base = StoredPolicyDecisionProvider(
            setup.event_store,
            RuntimePolicySetup(
                run_id=setup.run_id,
                manifests={b.skill_id: b.manifest for b in setup.manifests},
                structural_decisions=setup.decisions,
                enforcement_mode=scenario.execution.mode,
                auto_approve_tools=scenario.harness.auto_approve_tools,
                implicit_text_authorization=scenario.harness.implicit_text_authorization,
            ),
        )
        components = FIXED[self.mode]
        if self.mode == "oracle_router":
            selected = {d for label in self.skill.scoring_labels for d in ORACLE[label]}
            components = tuple(d for d in DEFENSE_ORDER if d in selected)
        if self.shadow:
            components = tuple(d for d in components if d != "causal")
        provider = DefendedDecisionProvider(
            setup.event_store,
            base,
            DefenseSetup(
                setup.run_id,
                self.skill.task_plan,
                self.skill.task_contract.risk_selectors,
                Treatment(
                    components, evidence_routing=self.mode == "evidence_router" and not self.shadow
                ),
                self.replay,
            ),
        )
        self.providers[setup.run_id] = provider
        dependencies = RuntimeDependencies(
            setup.event_store,
            setup.blob_store,
            VirtualClock(scenario.clock.start),
            DeterministicIdFactory(setup.seed),
            scenario.harness.provenance_mode,
        )
        harness = LiveReferenceHarnessAdapter(
            MockHarnessConfig(
                run_id=setup.run_id,
                task_id=scenario.task.id,
                workspace_root=setup.workspace,
                dependencies=dependencies,
                initial_grants=scenario.grants,
            ),
            backend,
            provider,
        )
        self.bindings[id(harness)] = capture
        return harness
