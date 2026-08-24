from pathlib import Path

from typer.testing import CliRunner

from skillflow.cli import app

runner = CliRunner()


def test_version_returns_success_when_invoked() -> None:
    # Given: 已安装的 SkillFlow CLI
    # When: 调用 version 命令
    result = runner.invoke(app, ["version"])

    # Then: 返回成功并输出稳定版本号
    assert result.exit_code == 0
    assert result.output.strip() == "SkillFlow 0.1.0"


def test_doctor_returns_success_when_temp_directory_is_writable(tmp_path: Path) -> None:
    # Given: 一个可写的临时目录
    # When: 调用 doctor 命令
    result = runner.invoke(app, ["doctor", "--temp-dir", str(tmp_path)])

    # Then: 返回成功且四项检查均通过
    assert result.exit_code == 0
    assert result.output.count("[通过]") == 4


def test_doctor_returns_failure_when_temp_path_is_invalid(tmp_path: Path) -> None:
    # Given: 一个文件路径，不能作为临时目录使用
    blocked_path = tmp_path / "not-a-directory"
    blocked_path.write_text("fixture", encoding="utf-8")

    # When: 调用 doctor 命令
    result = runner.invoke(app, ["doctor", "--temp-dir", str(blocked_path)])

    # Then: 返回失败并标明临时目录检查失败
    assert result.exit_code == 1
    assert "[失败] 临时目录" in result.output
