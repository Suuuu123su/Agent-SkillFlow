"""Mock Harness 的 Session 代理装配。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.instrumentation.context_proxy import InstrumentedContext
from skillflow.instrumentation.decision_stub import DecisionProvider
from skillflow.instrumentation.file_proxy import InstrumentedFile
from skillflow.instrumentation.memory_proxy import InstrumentedMemory, MemoryState
from skillflow.instrumentation.mock_tools import (
    MockNetworkSink,
    MockShellSink,
    MockToolAdapter,
    MockToolServices,
)
from skillflow.instrumentation.skill_proxy import InstrumentedSkill, SkillState
from skillflow.instrumentation.tool_proxy import InstrumentedTool
from skillflow.runtime.session import RuntimeDependencies, RuntimeRecorder, SessionIdentity


@dataclass(frozen=True, slots=True)
class MockSessionRuntime:
    """只在一个活动 Session 中可访问的代理集合。"""

    recorder: RuntimeRecorder
    context: InstrumentedContext
    memory: InstrumentedMemory
    files: InstrumentedFile
    skills: InstrumentedSkill
    tools: InstrumentedTool


@dataclass(frozen=True, slots=True)
class MockSessionSetup:
    """装配 Session 代理所需的 Run 级依赖。"""

    identity: SessionIdentity
    dependencies: RuntimeDependencies
    workspace_root: Path
    decisions: DecisionProvider
    memory_state: MemoryState
    skill_state: SkillState
    network: MockNetworkSink
    shell: MockShellSink


def create_mock_session(setup: MockSessionSetup) -> MockSessionRuntime:
    """创建代理但不追加任何生命周期 Event。"""
    recorder = RuntimeRecorder(setup.identity, setup.dependencies)
    files = InstrumentedFile(setup.workspace_root, recorder)
    memory = InstrumentedMemory(recorder, setup.memory_state)
    tools = InstrumentedTool(
        recorder,
        setup.decisions,
        MockToolAdapter(
            MockToolServices(
                files=files,
                memory=memory,
                network=setup.network,
                shell=setup.shell,
            )
        ),
    )
    return MockSessionRuntime(
        recorder=recorder,
        context=InstrumentedContext(recorder),
        memory=memory,
        files=files,
        skills=InstrumentedSkill(recorder, setup.skill_state),
        tools=tools,
    )
