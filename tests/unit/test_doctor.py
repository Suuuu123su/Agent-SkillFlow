from pathlib import Path
from unittest.mock import patch

from skillflow.cli import collect_doctor_checks


def test_doctor_checks_pass_when_environment_is_ready(tmp_path: Path) -> None:
    # Given: 一个可写的临时目录和已经安装的项目依赖
    # When: 收集环境检查结果
    checks = collect_doctor_checks(tmp_path)

    # Then: 所有检查通过且覆盖四个固定检查维度
    assert all(check.passed for check in checks)
    assert {check.name for check in checks} == {"Python", "SQLite", "依赖包", "临时目录"}


def test_doctor_reports_failure_when_temp_directory_is_not_writable(tmp_path: Path) -> None:
    # Given: 操作系统拒绝在目标临时目录中创建探测文件
    permission_error = PermissionError("fixture denied")

    # When: 收集环境检查结果
    with patch(
        "skillflow.cli.tempfile.NamedTemporaryFile",
        side_effect=permission_error,
    ):
        checks = collect_doctor_checks(tmp_path)

    # Then: 临时目录检查失败并给出可理解的原因
    temp_check = next(check for check in checks if check.name == "临时目录")
    assert not temp_check.passed
    assert "不可写或不可用" in temp_check.detail
