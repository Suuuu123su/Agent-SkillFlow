"""存储边界的结构化错误。"""

from dataclasses import dataclass


class StoreError(Exception):
    """SkillFlow 存储错误基类。"""


@dataclass(frozen=True, slots=True)
class StoreClosedError(StoreError):
    """资源关闭后仍尝试访问。"""

    resource: str

    def __str__(self) -> str:
        """返回关闭资源名称。"""
        return f"存储资源已关闭：{self.resource}"


@dataclass(frozen=True, slots=True)
class StoreConflictError(StoreError):
    """追加式实体 ID 已存在。"""

    entity: str
    identifier: str

    def __str__(self) -> str:
        """返回冲突实体及其 ID。"""
        return f"{self.entity} 已存在：{self.identifier}"


@dataclass(frozen=True, slots=True)
class StoreIntegrityError(StoreError):
    """一次写入违反引用或原子性约束。"""

    operation: str
    reason: str

    def __str__(self) -> str:
        """返回失败操作及完整性原因。"""
        return f"{self.operation} 违反存储完整性：{self.reason}"


@dataclass(frozen=True, slots=True)
class BlobScopeError(StoreError):
    """Blob 引用跨越固定 Run 作用域。"""

    expected_run_id: str
    actual_run_id: str

    def __str__(self) -> str:
        """返回期望与实际 Run。"""
        return f"Blob Run 不匹配：期望 {self.expected_run_id}，实际 {self.actual_run_id}"


@dataclass(frozen=True, slots=True)
class BlobIntegrityError(StoreError):
    """Blob 内容与不可变引用不一致。"""

    blob_id: str

    def __str__(self) -> str:
        """返回损坏或缺失的 Blob ID。"""
        return f"Blob 内容完整性校验失败：{self.blob_id}"
