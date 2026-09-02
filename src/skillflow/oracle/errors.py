"""Oracle sidecar 的类型化完整性错误。"""


class OracleInvariantError(Exception):
    """声明式真值无法机械闭合。"""

    __slots__ = ("operation", "reason")

    operation: str
    reason: str

    def __init__(self, operation: str, reason: str) -> None:
        """Store stable reason fields without freezing exception runtime state."""
        super().__init__(operation, reason)
        self.operation = operation
        self.reason = reason

    def __str__(self) -> str:
        """返回失败阶段与机械闭合原因。"""
        return f"Oracle 不变量失败：{self.operation}：{self.reason}"
