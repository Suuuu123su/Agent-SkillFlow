import ast
from pathlib import Path

GRAPH_ROOT = Path(__file__).parents[3] / "src" / "skillflow" / "graph"
FORBIDDEN_PREFIXES = (
    "skillflow.adapters",
    "skillflow.instrumentation",
    "skillflow.oracle",
    "skillflow.runtime",
    "skillflow.trace",
)


def imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return tuple(modules)


def test_graph_analysis_depends_only_on_models_store_and_networkx() -> None:
    paths = tuple(sorted(GRAPH_ROOT.glob("*.py")))

    imports = tuple(module for path in paths for module in imported_modules(path))

    assert paths
    assert not any(module.startswith(prefix) for module in imports for prefix in FORBIDDEN_PREFIXES)
