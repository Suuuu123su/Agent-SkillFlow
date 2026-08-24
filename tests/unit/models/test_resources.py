import pytest
from pydantic import ValidationError

from skillflow.models.resources import ResourceRef


@pytest.mark.parametrize(
    "uri",
    [
        "http://example.com/file",
        "workspace:",
        "workspace:/safe/../secret.txt",
        "workspace://host/share.txt",
        "C:\\secret.txt",
        "workspace:/C:/secret.txt",
        "workspace:\\secret.txt",
    ],
)
def test_resource_ref_rejects_unsafe_or_unknown_uri(uri: str) -> None:
    # Given: 一个未知、空、穿越或主机绝对路径 URI
    # When/Then: ResourceRef 在边界拒绝它
    with pytest.raises(ValidationError):
        ResourceRef(uri)


def test_resource_ref_normalizes_safe_posix_path() -> None:
    # Given: 一个包含重复分隔符和当前目录段的安全 URI
    # When: 解析为 ResourceRef
    resource = ResourceRef("workspace:/reports//./daily.md")

    # Then: 保存稳定的规范形式
    assert resource.root == "workspace:/reports/daily.md"


def test_exact_resource_match_does_not_use_string_prefix() -> None:
    # Given: 一个精确文件引用、其父目录和相邻前缀文件
    granted = ResourceRef("workspace:/reports/a.txt")
    parent = ResourceRef("workspace:/reports")
    neighbor = ResourceRef("workspace:/reports/a.txt.bak")

    # When/Then: 只覆盖完全相同的规范 URI
    assert granted.matches_exact(ResourceRef("workspace:/reports/a.txt"))
    assert not granted.matches_exact(parent)
    assert not granted.matches_exact(neighbor)
