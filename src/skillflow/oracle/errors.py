"""Oracle sidecar 的类型化完整性错误。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OracleInvariantError(Exception):
    """声明式真值无法机械闭合。"""

    operation: str
    reason: str

    def __str__(self) -> str:
        """返回失败阶段与机械闭合原因。"""
        return f"Oracle 不变量失败：{self.operation}：{self.reason}"
