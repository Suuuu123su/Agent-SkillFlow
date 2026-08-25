"""风险分析层的强类型一致性错误。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AnalysisInvariantError(Exception):
    """双轨或重复投影无法形成唯一结构化事实。"""

    operation: str
    detail: str

    def __str__(self) -> str:
        """返回分析阶段与冲突事实。"""
        return f"{self.operation}: {self.detail}"


@dataclass(frozen=True, slots=True)
class RiskReportWriteError(Exception):
    """风险报告无法按不可覆盖合同写入。"""

    path: Path
    detail: str

    def __str__(self) -> str:
        """返回目标路径与底层写入错误。"""
        return f"风险报告写入失败：{self.path}：{self.detail}"


@dataclass(frozen=True, slots=True)
class ReplayManifestWriteError(Exception):
    """反事实分支证据清单无法按不可覆盖合同写入。"""

    path: Path
    detail: str

    def __str__(self) -> str:
        """返回目标路径与底层写入错误。"""
        return f"Replay 清单写入失败：{self.path}：{self.detail}"
