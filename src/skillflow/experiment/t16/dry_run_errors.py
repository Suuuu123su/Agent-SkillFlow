"""T16-B 封闭设计与演练错误。"""

from dataclasses import dataclass
from enum import StrEnum, unique


@unique
class DryRunDesignReason(StrEnum):
    """矩阵执行或完整性失败原因。"""

    WRONG_MATRIX = "必须使用 360 链 model1 Matrix"
    UNKNOWN_CONDITION = "Matrix 引用了未知 condition"
    WRONG_TRIAL_COUNT = "实际调度数不等于预注册数"
    WRONG_INSTANCE_COUNT = "每个条件的语义实例数不一致"


@unique
class FailureRehearsalReason(StrEnum):
    """故障或费用演练未按预期收敛的原因。"""

    CLASSIFICATION_OVERLAP = "refusal 与 no-call 分类重叠"
    NETWORK_NOT_BLOCKED = "意外网络探针未被阻断"
    PROVIDER_KIND_DRIFT = "Provider 故障类型漂移"
    PROVIDER_NOT_FAILED = "Provider 故障没有触发"
    RECEIPT_ACCEPTED = "缺失 Receipt 未被拒绝"
    USAGE_ACCEPTED = "缺失 Token 信息未被拒绝"
    BUDGET_WRONG_LIMIT = "费用保护命中了错误边界"
    BUDGET_NOT_STOPPED = "费用保护没有停止"
    NOT_BUDGET_INJECTION = "请求的类型不是预算故障"
    TOO_FEW_RECORDS = "部分保存演练至少需要三条结果"
    PARTIAL_WRONG_LIMIT = "部分保存命中了错误预算边界"
    TOTAL_NOT_STOPPED = "总费用上限未在第三条前停止"
    SAMPLE_MISSING = "缺少所需三分类样例"


@dataclass(frozen=True, slots=True)
class DryRunDesignError(ValueError):
    """预注册结构不能形成封闭 Fake 行为。"""

    reason: DryRunDesignReason
    detail: str = ""

    def __str__(self) -> str:
        """返回稳定诊断。"""
        suffix = f": {self.detail}" if self.detail else ""
        return f"{self.reason.value}{suffix}"


@dataclass(frozen=True, slots=True)
class FailureRehearsalError(RuntimeError):
    """失败注入没有按预期被边界捕获。"""

    reason: FailureRehearsalReason
    detail: str = ""

    def __str__(self) -> str:
        """返回稳定诊断。"""
        suffix = f": {self.detail}" if self.detail else ""
        return f"{self.reason.value}{suffix}"
