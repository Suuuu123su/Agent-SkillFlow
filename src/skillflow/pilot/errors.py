"""T15 Pilot 的结构化边界错误。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PilotComparisonError(ValueError):
    """两个 Adapter 的观察不可比较。"""

    detail: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return self.detail

    @classmethod
    def scenario_mismatch(cls) -> "PilotComparisonError":
        """构造跨 Scenario 比较错误。"""
        return cls("两个 Adapter 的观察必须来自同一个 Scenario")


@dataclass(frozen=True, slots=True)
class PilotPlanError(ValueError):
    """Scenario 不能安全编译到封闭 OpenClaw 工具面。"""

    detail: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return self.detail

    @classmethod
    def fixture_missing(cls, skill_id: str) -> "PilotPlanError":
        """构造未注册 fixture 错误。"""
        return cls(f"fixture 未注册：{skill_id}")

    @classmethod
    def shell_forbidden(cls) -> "PilotPlanError":
        """构造 Shell 动作拒绝错误。"""
        return cls("T15 Pilot 禁止 Shell 动作")

    @classmethod
    def unsupported_asset(cls, resource: str) -> "PilotPlanError":
        """构造未知 asset URI 错误。"""
        return cls(f"不支持的 asset URI：{resource}")

    @classmethod
    def unsupported_file(cls, resource: str) -> "PilotPlanError":
        """构造非 Workspace 文件错误。"""
        return cls(f"不支持的文件资源：{resource}")

    @classmethod
    def unsafe_path(cls, value: str) -> "PilotPlanError":
        """构造路径逃逸错误。"""
        return cls(f"不安全的相对路径：{value}")

    @classmethod
    def marker_missing(cls) -> "PilotPlanError":
        """构造确定性 asset 标记缺失错误。"""
        return cls("T15 asset 必须提供确定性 marker")

    @classmethod
    def source_asset_count(cls) -> "PilotPlanError":
        """构造 Memory 来源 asset 数量错误。"""
        return cls("T15 Memory Pilot 只接受一个来源 asset")


@dataclass(frozen=True, slots=True)
class OpenClawEventFileError(ValueError):
    """OpenClaw 原始事件文件不是严格 JSONL。"""

    detail: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return self.detail

    @classmethod
    def blank_line(cls, line_number: int) -> "OpenClawEventFileError":
        """构造空行错误。"""
        return cls(f"第 {line_number} 行为空")

    @classmethod
    def invalid_line(cls, line_number: int, detail: str) -> "OpenClawEventFileError":
        """构造非法 JSONL 行错误。"""
        return cls(f"第 {line_number} 行无效：{detail}")

    @classmethod
    def sequence_invalid(cls) -> "OpenClawEventFileError":
        """构造非连续序号错误。"""
        return cls("事件序号必须从零开始且连续")

    @classmethod
    def effect_incomplete(cls) -> "OpenClawEventFileError":
        """构造转换阶段 Effect 字段缺失错误。"""
        return cls("通过验证的 Effect 丢失必需字段")


@dataclass(frozen=True, slots=True)
class OpenClawPilotError(RuntimeError):
    """真实 Harness 未能安全完成 Pilot。"""

    detail: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return self.detail

    @classmethod
    def driver_failed(cls, return_code: int, detail: str) -> "OpenClawPilotError":
        """构造外部 Driver 失败错误。"""
        return cls(f"OpenClaw Driver 失败（{return_code}）：{detail}")

    @classmethod
    def target_evidence_incomplete(cls) -> "OpenClawPilotError":
        """构造目标 Effect 证据不完整错误。"""
        return cls("目标 Effect 丢失必需证据")

    @classmethod
    def request_exists(cls, request_path: str) -> "OpenClawPilotError":
        """构造拒绝覆盖请求文件错误。"""
        return cls(f"OpenClaw 请求文件已存在，拒绝覆盖：{request_path}")


@dataclass(frozen=True, slots=True)
class PilotRunError(RuntimeError):
    """T15 三场景编排不能安全启动。"""

    detail: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return self.detail

    @classmethod
    def output_exists(cls, output_root: str) -> "PilotRunError":
        """构造拒绝覆盖证据目录错误。"""
        return cls(f"Pilot 输出目录已存在，拒绝覆盖：{output_root}")

    @classmethod
    def git_failed(cls, detail: str) -> "PilotRunError":
        """构造 OpenClaw revision 读取失败错误。"""
        return cls(f"无法读取 OpenClaw revision：{detail}")

    @classmethod
    def commit_mismatch(cls, actual: str, expected: str) -> "PilotRunError":
        """构造 OpenClaw revision 漂移错误。"""
        return cls(f"OpenClaw revision 不匹配：实际 {actual}，预期 {expected}")

    @classmethod
    def executable_missing(cls, name: str) -> "PilotRunError":
        """构造本机可执行文件缺失错误。"""
        return cls(f"找不到 T15 所需可执行文件：{name}")
