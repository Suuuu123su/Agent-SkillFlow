import ast
from pathlib import Path

import pytest

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
    {"httpx", "httpx2", "keyring", "requests", "socket", "subprocess", "urllib.request"}
)
T16C_APPROVED_EXTERNAL_IMPORTS = {
    Path("src/skillflow/experiment/t16/httpx2_transport.py"): frozenset({"httpx2", "socket"}),
    Path("src/skillflow/experiment/t17/v2/network.py"): frozenset({"httpx2"}),
}
T16C_APPROVED_SECRET_READERS = {
    Path("src/skillflow/experiment/t19/host.py"): frozenset({("getpass", "getpass")}),
    Path("src/skillflow/experiment/t16/live_cli.py"): frozenset({("getpass", "getpass")}),
    Path("src/skillflow/experiment/t16/task_success_live_cli.py"): frozenset({("os", "environ")}),
    Path("src/skillflow/experiment/t16/task_success_canary_cli.py"): frozenset({("os", "environ")}),
    Path("src/skillflow/experiment/t17/live_supervisor.py"): frozenset({("getpass", "getpass")}),
    Path("src/skillflow/experiment/t17/v2/campaign.py"): frozenset({("getpass", "getpass")}),
}


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


@pytest.mark.parametrize(
    ("relative", "source", "expected_counts"),
    [
        ("experiment/t17/v2/network.py", "import httpx2\nimport socket\n", (1, 0)),
        (
            "experiment/t17/v2/campaign.py",
            "import getpass\nimport os\ngetpass.getpass()\nos.environ.get('API_KEY')\n",
            (0, 1),
        ),
        ("runtime/not_approved.py", "import httpx2\nimport getpass\ngetpass.getpass()\n", (1, 1)),
        (
            "experiment/t19/host.py",
            (
                "import httpx2\nimport getpass\nimport os\nfrom pathlib import Path\n"
                "getpass.getpass()\nos.environ.get('API_KEY')\nPath.home()\n"
            ),
            (1, 2),
        ),
        ("experiment/t19/live.py", "import httpx2\nimport getpass\ngetpass.getpass()\n", (1, 1)),
    ],
)
def test_v2_entry_exceptions_do_not_allow_other_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    source: str,
    expected_counts: tuple[int, int],
) -> None:
    monkeypatch.chdir(tmp_path)
    path = Path("src/skillflow") / relative
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    assert (
        len(_external_imports(path)),
        len(_credential_or_home_accesses(path)),
    ) == expected_counts


def _oracle_imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return tuple(
        f"{path}:{node.lineno}"
        for node in ast.walk(tree)
        if _imports_module(node, "skillflow.oracle")
    )


def _external_imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    approved = T16C_APPROVED_EXTERNAL_IMPORTS.get(path, frozenset())
    return tuple(
        f"{path}:{node.lineno}"
        for node in ast.walk(tree)
        if any(
            module not in approved and _imports_module(node, module)
            for module in EXTERNAL_CAPABILITY_MODULES
        )
    )


def _credential_or_home_accesses(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    approved = T16C_APPROVED_SECRET_READERS.get(path, frozenset())
    return tuple(
        f"{path}:{node.lineno}"
        for node in ast.walk(tree)
        if _is_credential_or_home_access(node, approved)
    )


def _is_credential_or_home_access(
    node: ast.AST,
    approved: frozenset[tuple[str, str]],
) -> bool:
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name):
            access = (node.value.id, node.attr)
            return access not in approved and access in {
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


def test_t19_secret_input_is_confined_to_trusted_main() -> None:
    path = Path("src/skillflow/experiment/t19/host.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    reads = tuple(n for n in ast.walk(tree) if _is_credential_or_home_access(n, frozenset()))
    assert len(reads) == 1
    assert reads[0] in tuple(ast.walk(main))
    violations = []
    for root in (*EXECUTION_BOUNDARIES, Path("src/skillflow/defense")):
        for candidate in root.rglob("*.py"):
            if candidate == path:
                continue
            parsed = ast.parse(candidate.read_text(encoding="utf-8"))
            for node in ast.walk(parsed):
                from_parent = (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "skillflow.experiment.t19"
                    and any(alias.name == "host" for alias in node.names)
                )
                if _imports_module(node, "skillflow.experiment.t19.host") or from_parent:
                    violations.append(str(candidate))
    assert violations == []
