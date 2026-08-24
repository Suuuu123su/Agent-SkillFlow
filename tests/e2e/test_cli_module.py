import subprocess
import sys


def test_module_help_lists_commands_when_invoked_as_process() -> None:
    # Given: 当前测试解释器中已安装 SkillFlow
    # When: 通过真实 Python 进程请求模块帮助
    result = subprocess.run(
        [sys.executable, "-m", "skillflow.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: 进程成功并列出稳定的命令名
    assert result.returncode == 0
    assert "doctor" in result.stdout
    assert "version" in result.stdout
