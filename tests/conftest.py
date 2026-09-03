"""仅为受项目写入边界约束的 CLI 测试提供独占输出目录。"""

from pathlib import Path
from tempfile import mkdtemp

import pytest


@pytest.fixture(scope="module")
def t17_cli_root() -> Path:
    # pytest 的默认系统临时目录可能位于仓库外；不放宽真实 CLI 的路径保护。
    parent = Path.cwd() / ".tmp"
    parent.mkdir(exist_ok=True)
    return Path(mkdtemp(prefix="t17-cli-regression-", dir=parent))
