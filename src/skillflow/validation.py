"""YAML 文档的类型化加载与结构化错误报告。"""

from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """一个可以稳定断言的文档校验问题。"""

    file: Path
    field_path: str
    code: str
    reason: str

    def render(self) -> str:
        """输出同时适合人读和测试解析的单行错误。"""
        return f"[失败] 文件={self.file} 字段={self.field_path} 代码={self.code} 原因={self.reason}"


class DocumentValidationError(Exception):
    """包含一个文档全部已发现校验问题的异常。"""

    issues: tuple[ValidationIssue, ...]

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        """保留结构化问题并初始化异常消息。"""
        self.issues = issues
        super().__init__("; ".join(issue.render() for issue in issues))


def _field_path(location: tuple[str | int, ...]) -> str:
    path = "$"
    for segment in location:
        path = f"{path}[{segment}]" if isinstance(segment, int) else f"{path}.{segment}"
    return path


def _single_issue(path: Path, code: str, reason: str) -> DocumentValidationError:
    return DocumentValidationError(
        (ValidationIssue(file=path, field_path="$", code=code, reason=reason),)
    )


def validate_yaml_document(path: Path, model_type: type[ModelT]) -> ModelT:
    """读取 YAML 并在指定 Pydantic 模型边界完成校验。"""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as error:
        reason = error.strerror if error.strerror is not None else error.__class__.__name__
        raise _single_issue(path, "file_read_error", reason) from error
    except UnicodeError as error:
        raise _single_issue(path, "file_encoding_error", str(error)) from error

    try:
        payload = yaml.safe_load(raw_text)
    except yaml.YAMLError as error:
        raise _single_issue(path, "yaml_parse_error", str(error)) from error

    try:
        return model_type.model_validate(payload)
    except ValidationError as error:
        issues = tuple(
            ValidationIssue(
                file=path,
                field_path=_field_path(item["loc"]),
                code=item["type"],
                reason=item["msg"],
            )
            for item in error.errors()
        )
        raise DocumentValidationError(issues) from error
