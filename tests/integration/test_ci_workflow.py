from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]


def test_ci_installs_live_extra_before_collecting_the_full_suite() -> None:
    # Given
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )

    # When
    steps = workflow["jobs"]["quality"]["steps"]
    install_command = next(
        step["run"] for step in steps if step.get("name") == "安装项目与开发依赖"
    )

    # Then
    assert install_command == 'python -m pip install -e ".[dev,live]"'
