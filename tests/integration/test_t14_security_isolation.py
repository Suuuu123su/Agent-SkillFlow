import ast
from pathlib import Path

RUNTIME_BOUNDARIES = (Path("src/skillflow/runtime"), Path("src/skillflow/policy"))
EXECUTION_BOUNDARIES = (
    Path("src/skillflow/runtime"),
    Path("src/skillflow/policy"),
    Path("src/skillflow/instrumentation"),
    Path("src/skillflow/adapters"),
    Path("src/skillflow/benchmark"),
    Path("src/skillflow/experiment"),
)
EXTERNAL_CAPABILITY_MODULES = frozenset(
    {"httpx", "keyring", "requests", "socket", "subprocess", "urllib.request"}
)


def test_runtime_and_policy_cannot_import_oracle() -> None:
    violations = tuple(
        location
        for root in RUNTIME_BOUNDARIES
        for path in root.rglob("*.py")
        for location in _oracle_imports(path)
    )

    assert violations == ()


def test_execution_boundaries_have_no_real_external_capability_imports() -> None:
    violations = tuple(
        location
        for root in EXECUTION_BOUNDARIES
        for path in root.rglob("*.py")
        for location in (*_external_imports(path), *_credential_or_home_accesses(path))
    )

    assert violations == ()


def _oracle_imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return tuple(
        f"{path}:{node.lineno}"
        for node in ast.walk(tree)
        if _imports_module(node, "skillflow.oracle")
    )


def _external_imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return tuple(
        f"{path}:{node.lineno}"
        for node in ast.walk(tree)
        if any(_imports_module(node, module) for module in EXTERNAL_CAPABILITY_MODULES)
    )


def _credential_or_home_accesses(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return tuple(
        f"{path}:{node.lineno}" for node in ast.walk(tree) if _is_credential_or_home_access(node)
    )


def _is_credential_or_home_access(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name):
            return (node.value.id, node.attr) in {
                ("Path", "home"),
                ("getpass", "getpass"),
                ("os", "environ"),
                ("os", "getenv"),
                ("os", "getlogin"),
            }
        return node.attr == "expanduser"
    return False


def _imports_module(node: ast.AST, target: str) -> bool:
    if isinstance(node, ast.Import):
        return any(
            alias.name == target or alias.name.startswith(f"{target}.") for alias in node.names
        )
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return node.module == target or node.module.startswith(f"{target}.")
    return False
