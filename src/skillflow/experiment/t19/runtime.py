"""T19 在既有 Safe Sink、事件库、回执与检查点上装配独立防御。"""

from dataclasses import dataclass, field

from skillflow.adapters.mock_harness import MockHarnessAdapter, MockHarnessConfig
from skillflow.benchmark.execution_policy import ScenarioExecutionPolicy
from skillflow.benchmark.harness_factory import HarnessFactorySetup
from skillflow.benchmark.scenario_execution import ScenarioExecutor, ScenarioExecutorSetup
from skillflow.benchmark.scripted_backend import ScriptedBackend
from skillflow.defense.rx import Component, TaskConstraints, TreatmentName
from skillflow.defense.rx_provider import RxDecisionProvider, RxSetup
from skillflow.experiment.t17.reference_backend import ReferenceModelClient, ReferenceRunContext
from skillflow.experiment.t17.v2.runtime_models import RunCapture
from skillflow.experiment.t19.boundaries import BoundaryIssue, RxScenarioExecutor
from skillflow.experiment.t19.harness import RxHarnessAdapter
from skillflow.experiment.t19.recovery import RecoveryBackend
from skillflow.models.enums import EnforcementMode
from skillflow.policy.runtime import RuntimePolicySetup, StoredPolicyDecisionProvider
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import RuntimeDependencies


@dataclass(slots=True)
class RxHarnessFactory:
    """只接收可信任务与组配置；评分目标留在实验器侧。"""

    task: TaskConstraints
    treatment: TreatmentName
    client: ReferenceModelClient | None = None
    fixed: tuple[Component, ...] = ()
    bridge_data_only: bool = False
    replay_prefix_steps: dict[str, int] = field(default_factory=dict)
    boundary_issues: dict[str, list[BoundaryIssue]] = field(default_factory=dict)
    captures: dict[str, RunCapture] = field(default_factory=dict)
    providers: dict[str, RxDecisionProvider] = field(default_factory=dict)
    bindings: dict[int, RunCapture] = field(default_factory=dict)
    backends: dict[str, RecoveryBackend] = field(default_factory=dict)

    @property
    def execution_policy(self) -> ScenarioExecutionPolicy:
        """依赖缺失记录为失败，后续独立步骤按原预算继续。"""
        return ScenarioExecutionPolicy(self.executor, validate_scripted_expectations=False)

    def executor(self, setup: ScenarioExecutorSetup) -> ScenarioExecutor:
        """保留原Run绑定与现场检查点。"""
        if isinstance(setup.harness, RxHarnessAdapter) and setup.oracle is not None:
            setup.harness.derivation_observer = setup.oracle.record_derivation
        capture = self.bindings[id(setup.harness)]
        return RxScenarioExecutor(setup, capture, self.boundary_issues[capture.run_id])

    def __call__(self, setup: HarnessFactorySetup) -> MockHarnessAdapter:
        """不替换工具执行器，不把目标选择器送入防御。"""
        capture = RunCapture(setup.run_id, capture_checkpoints=True)
        self.captures[setup.run_id] = capture
        self.boundary_issues[setup.run_id] = []
        backend = (
            ScriptedBackend(setup.scripts)
            if self.client is None
            else RecoveryBackend(
                setup.scripts,
                self.client,
                ReferenceRunContext("opaque-task", setup.scenario.task.prompt),
                capture,
                setup.event_store,
            )
        )
        if isinstance(backend, RecoveryBackend):
            self.backends[setup.run_id] = backend
        base = StoredPolicyDecisionProvider(
            setup.event_store,
            RuntimePolicySetup(
                run_id=setup.run_id,
                manifests={b.skill_id: b.manifest for b in setup.manifests},
                structural_decisions=setup.decisions,
                enforcement_mode=EnforcementMode.MONITOR,
                auto_approve_tools=setup.scenario.harness.auto_approve_tools,
                implicit_text_authorization=setup.scenario.harness.implicit_text_authorization,
            ),
        )
        provider = RxDecisionProvider(
            setup.event_store,
            base,
            RxSetup(setup.run_id, self.task, self.treatment, self.fixed),
        )
        self.providers[setup.run_id] = provider
        dependencies = RuntimeDependencies(
            setup.event_store,
            setup.blob_store,
            VirtualClock(setup.scenario.clock.start),
            DeterministicIdFactory(setup.seed),
            setup.scenario.harness.provenance_mode,
        )
        harness = RxHarnessAdapter(
            MockHarnessConfig(
                run_id=setup.run_id,
                task_id=setup.scenario.task.id,
                workspace_root=setup.workspace,
                dependencies=dependencies,
                initial_grants=setup.scenario.grants,
            ),
            backend,
            provider,
        )
        harness.bridge_data_only = self.bridge_data_only
        self.bindings[id(harness)] = capture
        return harness
