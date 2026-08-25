"""T13 命令边界使用的稳定错误码。"""

from dataclasses import dataclass
from enum import IntEnum, StrEnum, unique


@unique
class CommandExitCode(IntEnum):
    """研究工作流命令的稳定进程退出码。"""

    INPUT_INVALID = 2
    NOT_FOUND = 3
    OUTPUT_CONFLICT = 4
    EXECUTION_FAILED = 5


@unique
class ExperimentErrorCode(StrEnum):
    """可供人和自动化共同解析的实验错误码。"""

    NOT_IMPLEMENTED = "t13_not_implemented"
    INPUT_OUTSIDE_REGISTRY = "input_outside_registry"
    INPUT_VALUE_INVALID = "input_value_invalid"
    RESOURCE_NOT_FOUND = "resource_not_found"
    OUTPUT_EXISTS = "output_exists"
    EXECUTION_FAILED = "execution_failed"


@dataclass(frozen=True, slots=True)
class ExperimentCommandError(Exception):
    """一个已知、可安全呈现的实验命令失败。"""

    code: ExperimentErrorCode
    detail: str
    exit_code: CommandExitCode

    def __str__(self) -> str:
        """返回不含内部堆栈或原始内容的错误说明。"""
        return f"代码={self.code.value} 原因={self.detail}"
