from pathlib import Path

from typer.testing import CliRunner

from skillflow.cli import app

runner = CliRunner()
FIXTURE_DIR = Path("tests/fixtures/t03")


def test_validate_manifest_accepts_valid_fixture() -> None:
    path = FIXTURE_DIR / "valid_manifest.yaml"

    result = runner.invoke(app, ["validate-manifest", str(path)])

    assert result.exit_code == 0
    assert "[通过]" in result.output
    assert str(path) in result.output


def test_validate_scenario_accepts_valid_fixture() -> None:
    path = FIXTURE_DIR / "valid_scenario.yaml"

    result = runner.invoke(app, ["validate-scenario", str(path)])

    assert result.exit_code == 0
    assert "[通过]" in result.output
    assert str(path) in result.output


def test_validate_manifest_reports_file_field_code_and_reason(tmp_path: Path) -> None:
    path = tmp_path / "invalid-manifest.yaml"
    path.write_text(
        """
schema_version: "0.1"
principal_type: skill
requested_permissions:
  - source: C:/secret.txt
    action: file.teleport
    sink: mock://external
    scope: exact-file
    lifetime: forever
    sensitivity: 4
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["validate-manifest", str(path)])

    assert result.exit_code == 2
    assert f"文件={path}" in result.output
    assert "字段=$.id" in result.output
    assert "字段=$.requested_permissions[0].lifetime" in result.output
    assert "代码=" in result.output
    assert "原因=" in result.output


def test_validate_scenario_reports_unsafe_implementation_path(tmp_path: Path) -> None:
    valid_path = FIXTURE_DIR / "valid_scenario.yaml"
    unsafe_path = tmp_path / "unsafe-scenario.yaml"
    unsafe_path.write_text(
        valid_path.read_text(encoding="utf-8").replace(
            "fixture://safe_reader",
            "C:/skills/safe_reader.py",
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["validate-scenario", str(unsafe_path)])

    assert result.exit_code == 2
    assert f"文件={unsafe_path}" in result.output
    assert "字段=$.skills[0].implementation" in result.output
    assert "原因=" in result.output


def test_validate_command_reports_yaml_parse_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("id: [", encoding="utf-8")

    result = runner.invoke(app, ["validate-manifest", str(path)])

    assert result.exit_code == 2
    assert f"文件={path}" in result.output
    assert "字段=$" in result.output
    assert "代码=yaml_parse_error" in result.output
