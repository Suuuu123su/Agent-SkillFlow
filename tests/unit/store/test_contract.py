from importlib import import_module
from importlib.util import find_spec

import pytest


def test_store_package_exists_for_t04_contract() -> None:
    # Given: 已完成 T03、尚未实现 T04 的 SkillFlow 包
    # When: 查找 T04 的 store 包
    package = find_spec("skillflow.store")

    # Then: T04 必须提供独立存储边界
    assert package is not None


@pytest.mark.parametrize(
    "module_name",
    [
        "skillflow.store.event_store",
        "skillflow.store.sqlite_store",
        "skillflow.store.blob_store",
        "skillflow.store.trace",
        "skillflow.runtime.determinism",
    ],
)
def test_t04_contract_modules_exist(module_name: str) -> None:
    # Given: T04 要求的存储、Blob、Trace 和确定性组件
    # When: 查找对应模块
    module = find_spec(module_name)

    # Then: 每项职责都有独立模块边界
    assert module is not None


@pytest.mark.parametrize(
    ("module_name", "public_names"),
    [
        (
            "skillflow.store.event_store",
            ("EventEnvelope", "EventStore", "MemoryHead", "StoredArtifact"),
        ),
        ("skillflow.store.sqlite_store", ("SqliteEventStore",)),
        ("skillflow.store.blob_store", ("BlobRef", "RunBlobStore")),
        ("skillflow.store.trace", ("RunTrace", "build_run_trace")),
        (
            "skillflow.runtime.determinism",
            ("Clock", "DeterministicIdFactory", "IdFactory", "VirtualClock"),
        ),
    ],
)
def test_t04_modules_expose_typed_contracts(
    module_name: str,
    public_names: tuple[str, ...],
) -> None:
    # Given: 已存在的 T04 职责模块
    module = import_module(module_name)

    # When: 读取其公开合同名
    available = frozenset(vars(module))

    # Then: 后续测试不依赖私有实现细节
    assert frozenset(public_names) <= available
