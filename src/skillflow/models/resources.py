"""受控 Resource URI 值对象。"""

import re
from typing import Final

from pydantic import ConfigDict, RootModel, field_validator
from pydantic_core import PydanticCustomError

ALLOWED_SCHEMES: Final = frozenset({"workspace", "context", "memory", "mock", "fixture"})
AUTHORITY_SCHEMES: Final = frozenset({"mock", "fixture"})
URI_PATTERN: Final = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*):(?P<resource>.*)")
WINDOWS_DRIVE_PATTERN: Final = re.compile(r"[A-Za-z]:")


def _invalid_resource(code: str, reason: str) -> PydanticCustomError:
    return PydanticCustomError(code, "{reason}", {"reason": reason})


class ResourceRef(RootModel[str]):
    """一个已经校验并规范化的 Resource URI。"""

    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def normalize_uri(cls, value: str) -> str:
        """在输入边界规范化 URI 并拒绝主机路径或路径穿越。"""
        if "\\" in value or "\x00" in value or "?" in value or "#" in value:
            raise _invalid_resource("resource_uri_unsafe", "URI 含有禁止的字符")

        matched = URI_PATTERN.fullmatch(value.strip())
        if matched is None:
            raise _invalid_resource("resource_uri_invalid", "URI 缺少合法 scheme")

        scheme = matched.group("scheme").lower()
        resource = matched.group("resource")
        if scheme not in ALLOWED_SCHEMES:
            raise _invalid_resource("resource_scheme_unknown", f"未知 scheme: {scheme}")
        if not resource:
            raise _invalid_resource("resource_scope_empty", "资源 scope 不能为空")

        authority_style = resource.startswith("//")
        if authority_style and scheme not in AUTHORITY_SCHEMES:
            raise _invalid_resource("resource_host_path_forbidden", "该 scheme 禁止主机路径")
        if not authority_style and not resource.startswith("/"):
            raise _invalid_resource("resource_path_invalid", "资源路径必须以 / 开始")

        prefix = "//" if authority_style else "/"
        raw_segments = resource[len(prefix) :].split("/")
        if ".." in raw_segments:
            raise _invalid_resource("resource_path_traversal", "资源路径禁止 ..")
        segments = tuple(segment for segment in raw_segments if segment not in {"", "."})
        if not segments:
            raise _invalid_resource("resource_scope_empty", "资源 scope 不能为空")
        if WINDOWS_DRIVE_PATTERN.fullmatch(segments[0]) is not None:
            raise _invalid_resource("resource_host_path_forbidden", "资源路径禁止 Windows 盘符")
        return f"{scheme}:{prefix}{'/'.join(segments)}"

    def matches_exact(self, requested: "ResourceRef") -> bool:
        """判断两个引用是否指向同一个精确资源。"""
        return self.root == requested.root
