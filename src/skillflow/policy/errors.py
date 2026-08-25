"""Policy 配置边界的类型化错误。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PolicyConfigurationError(Exception):
    """运行期缺少 Manifest 或结构基线 fixture。"""

    key: str
    reason: str

    def __str__(self) -> str:
        """返回稳定、可读的配置错误。"""
        return f"Policy 配置 {self.key!r} 无效：{self.reason}"
