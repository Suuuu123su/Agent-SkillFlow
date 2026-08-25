from pathlib import Path

from typer.testing import CliRunner

from skillflow.cli import app

runner = CliRunner()


def test_t13_help_lists_research_workflow_commands() -> None:
    # Given: 已安装的 SkillFlow CLI
    # When: 请求根命令帮助
    result = runner.invoke(app, ["--help"])

    # Then: T13 的完整研究工作流命令均可发现
    assert result.exit_code == 0
    for command in (
        "run",
        "analyze",
        "graph",
        "factorial",
        "matrix",
        "replay",
        "aggregate",
        "export",
    ):
        assert command in result.output


def test_matrix_reports_a_structured_document_error_for_missing_input(
    tmp_path: Path,
) -> None:
    # Given: 一个不存在的 Matrix YAML
    missing = tmp_path / "missing.yaml"

    # When: 调用 matrix 命令
    result = runner.invoke(app, ["matrix", str(missing)])

    # Then: 使用统一的输入错误码和人类可读原因
    assert result.exit_code == 2
    assert "代码=file_read_error" in result.output
    assert "原因=" in result.output
