import ast
import inspect
from pathlib import Path

from skillflow.adapters.base import HarnessSession, SkillInvocation, SkillInvocationResult
from skillflow.benchmark.scripted_backend import ScriptedBackend
from skillflow.instrumentation.tool_types import ToolCallRequest

PROJECT_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src" / "skillflow"


def imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return tuple(modules)


def test_runtime_and_observed_components_do_not_import_oracle() -> None:
    # Given: Agent/Skill/Policy/Observed 所在的运行组件目录
    component_roots = (
        SOURCE_ROOT / "adapters",
        SOURCE_ROOT / "instrumentation",
        SOURCE_ROOT / "runtime",
        SOURCE_ROOT / "store",
        SOURCE_ROOT / "trace",
    )
    component_files = tuple(
        path
        for root in component_roots
        if root.exists()
        for path in root.rglob("*.py")
        if path.name != "__init__.py"
    )

    # When: 静态审计直接 import 边
    violations = tuple(
        (path.relative_to(PROJECT_ROOT), module)
        for path in component_files
        for module in imported_modules(path)
        if module == "skillflow.oracle" or module.startswith("skillflow.oracle.")
    )

    # Then: 被测运行面不存在反向 Oracle 依赖
    assert component_files
    assert violations == ()


def test_oracle_package_does_not_import_runtime_or_defense_implementations() -> None:
    # Given: 独立 Oracle 包
    oracle_root = SOURCE_ROOT / "oracle"
    oracle_files = tuple(oracle_root.rglob("*.py"))
    forbidden_prefixes = (
        "skillflow.adapters",
        "skillflow.instrumentation",
        "skillflow.runtime",
        "skillflow.store",
        "skillflow.trace.observed",
    )

    # When: 审计 Oracle 的直接依赖
    violations = tuple(
        (path.relative_to(PROJECT_ROOT), module)
        for path in oracle_files
        for module in imported_modules(path)
        if module.startswith(forbidden_prefixes)
    )

    # Then: Oracle 只依赖中立合同，不形成防御实现循环
    assert oracle_files
    assert violations == ()


def test_agent_skill_and_tool_interfaces_expose_no_oracle_type() -> None:
    # Given: Skill/Harness/Tool 能够接触的公开类型和调用签名
    interfaces = (
        HarnessSession,
        SkillInvocation,
        SkillInvocationResult,
        ToolCallRequest,
        ScriptedBackend.invoke,
    )

    # When: 检查注解和签名文本
    rendered = "\n".join(
        str(inspect.signature(item)) if callable(item) else str(item.__annotations__)
        for item in interfaces
    ).lower()

    # Then: 任何可见接口都拿不到 Oracle 对象
    assert "oracle" not in rendered
