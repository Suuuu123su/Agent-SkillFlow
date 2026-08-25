from importlib import import_module
from importlib.util import find_spec

import pytest


def test_t05_top_level_packages_exist() -> None:
    # Given: 已完成 T04、尚未实现 T05 的 SkillFlow 包
    package_names = (
        "skillflow.adapters",
        "skillflow.instrumentation",
        "skillflow.benchmark",
    )

    # When: 查找 T05 的 Adapter、插桩和 Benchmark 包
    packages = tuple(find_spec(name) for name in package_names)

    # Then: 三类职责必须有独立包边界
    assert all(package is not None for package in packages)


@pytest.mark.parametrize(
    "module_name",
    [
        "skillflow.adapters.base",
        "skillflow.adapters.mock_harness",
        "skillflow.benchmark.scripted_backend",
        "skillflow.benchmark.runner",
        "skillflow.runtime.session",
        "skillflow.instrumentation.errors",
        "skillflow.instrumentation.context_proxy",
        "skillflow.instrumentation.memory_proxy",
        "skillflow.instrumentation.file_proxy",
        "skillflow.instrumentation.skill_proxy",
        "skillflow.instrumentation.tool_types",
        "skillflow.instrumentation.tool_proxy",
        "skillflow.instrumentation.tool_receipt",
        "skillflow.instrumentation.mock_tools",
    ],
)
def test_t05_responsibility_modules_exist(module_name: str) -> None:
    # Given: T05 要求的 Adapter、运行时、插桩与编排职责
    # When: 查找对应模块
    module = find_spec(module_name)

    # Then: 每项职责必须有独立模块，不能堆进单一 Harness 文件
    assert module is not None


@pytest.mark.parametrize(
    ("module_name", "public_names"),
    [
        (
            "skillflow.adapters.base",
            (
                "HarnessAdapter",
                "CheckpointableHarnessAdapter",
                "HarnessSession",
                "SkillBinding",
                "SkillInvocation",
                "SkillInvocationResult",
            ),
        ),
        (
            "skillflow.adapters.mock_harness",
            ("BenchmarkController", "MockHarnessAdapter", "MockHarnessConfig"),
        ),
        (
            "skillflow.benchmark.scripted_backend",
            ("FixtureScript", "ScriptedBackend", "ToolScriptAction"),
        ),
        (
            "skillflow.benchmark.runner",
            ("ScenarioRunResult", "ScenarioRunner"),
        ),
        (
            "skillflow.runtime.session",
            (
                "ActorCall",
                "ArtifactEmission",
                "EventEmission",
                "RuntimeDependencies",
                "RuntimeRecorder",
                "SessionIdentity",
            ),
        ),
        (
            "skillflow.instrumentation.errors",
            (
                "ArtifactContentError",
                "DecisionFixtureError",
                "FixtureNotFoundError",
                "HarnessStateError",
                "MemoryKeyMissingError",
                "ReceiptAuthorityError",
                "SkillLifecycleError",
                "UnsupportedStepError",
                "WorkspaceEscapeError",
                "WorkspaceResourceError",
            ),
        ),
        ("skillflow.instrumentation.context_proxy", ("InstrumentedContext",)),
        (
            "skillflow.instrumentation.memory_proxy",
            ("InstrumentedMemory", "MemoryState"),
        ),
        ("skillflow.instrumentation.file_proxy", ("InstrumentedFile",)),
        (
            "skillflow.instrumentation.skill_proxy",
            ("InstrumentedSkill", "SkillState"),
        ),
        (
            "skillflow.instrumentation.tool_types",
            (
                "HttpSendArgs",
                "MockToolName",
                "ReadFileArgs",
                "ReadMemoryArgs",
                "ShellExecArgs",
                "ToolCallRequest",
                "WriteMemoryArgs",
            ),
        ),
        (
            "skillflow.instrumentation.tool_proxy",
            (
                "AllowedToolCall",
                "DeniedToolCall",
                "ExecutedToolCall",
                "InstrumentedTool",
                "StubDecisionProvider",
                "ToolCallRequest",
            ),
        ),
        ("skillflow.instrumentation.tool_receipt", ("ToolReceipt",)),
        (
            "skillflow.instrumentation.mock_tools",
            ("MockNetworkSink", "MockShellSink", "MockToolAdapter", "MockToolServices"),
        ),
    ],
)
def test_t05_modules_expose_typed_contracts(
    module_name: str,
    public_names: tuple[str, ...],
) -> None:
    # Given: 已存在的 T05 职责模块
    module = import_module(module_name)

    # When: 读取其公开合同名
    available = frozenset(vars(module))

    # Then: 后续测试只依赖稳定公开合同
    assert frozenset(public_names) <= available
