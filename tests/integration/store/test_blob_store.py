import hashlib
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.store.blob_store import BlobRef, RunBlobStore
from skillflow.store.errors import BlobScopeError, StoreClosedError

SECRET = b"T04_TEST_SECRET_DO_NOT_EXPORT"


def test_blob_store_persists_content_without_exposing_a_path(tmp_path: Path) -> None:
    # Given: 一个固定到 run-1 的受控 BlobStore
    store = RunBlobStore(tmp_path, "run-1")

    # When: 写入运行态秘密并关闭后重新打开
    reference = store.put(SECRET)
    store.flush()
    store.close()
    reopened = RunBlobStore(tmp_path, "run-1")
    restored = reopened.get(reference)
    reopened.close()

    # Then: 引用只有不透明 ID、hash 和长度，内容可恢复
    assert restored == SECRET
    assert re.fullmatch(r"[0-9a-f]{48}", reference.blob_id)
    assert reference.content_hash == hashlib.sha256(SECRET).hexdigest()
    assert reference.content_length == len(SECRET)
    assert not hasattr(reference, "path")


def test_blob_store_rejects_cross_run_reference(tmp_path: Path) -> None:
    # Given: 两个独立 Run 的 BlobStore
    first = RunBlobStore(tmp_path, "run-1")
    second = RunBlobStore(tmp_path, "run-2")
    reference = first.put(SECRET)

    # When/Then: run-2 不能读取 run-1 的引用
    with pytest.raises(BlobScopeError):
        second.get(reference)
    first.close()
    second.close()


def test_blob_reference_rejects_path_syntax() -> None:
    # Given: 一个试图把相对路径伪装成 blob_id 的引用
    payload = {
        "run_id": "run-1",
        "blob_id": "../secret.txt",
        "content_hash": "sha256",
        "content_length": 1,
    }

    # When/Then: Pydantic 边界在文件系统访问前拒绝它
    with pytest.raises(ValidationError):
        BlobRef.model_validate(payload)


def test_blob_store_rejects_access_after_close(tmp_path: Path) -> None:
    # Given: 已关闭的 BlobStore
    store = RunBlobStore(tmp_path, "run-1")
    store.close()

    # When/Then: 后续写入不会静默重开资源
    with pytest.raises(StoreClosedError):
        store.put(SECRET)
