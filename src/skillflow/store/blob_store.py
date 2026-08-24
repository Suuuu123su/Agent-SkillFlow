"""按 Run 隔离的受控 BlobStore。"""

import hashlib
import os
import secrets
from pathlib import Path
from types import TracebackType
from typing import Annotated, Self

from pydantic import Field, StringConstraints

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.store.errors import BlobIntegrityError, BlobScopeError, StoreClosedError

BlobId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{48}$")]
ContentHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class BlobRef(StrictModel):
    """不暴露文件路径的运行态内容引用。"""

    run_id: NonEmptyStr
    blob_id: BlobId
    content_hash: ContentHash
    content_length: Annotated[int, Field(ge=0)]


class RunBlobStore:
    """一个按 Run 固定作用域的 Blob 资源。"""

    def __init__(self, experiment_root: Path, run_id: str) -> None:
        """在 Experiment 根内建立不可由外部路径控制的 Run 命名空间。"""
        run_namespace = hashlib.sha256(run_id.encode()).hexdigest()[:32]
        self._directory = experiment_root / "blobs" / run_namespace
        self._directory.mkdir(parents=True, exist_ok=True)
        self._run_id = run_id
        self._closed = False

    def __enter__(self) -> Self:
        """进入受控 Blob 资源上下文。"""
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出上下文时关闭逻辑资源。"""
        self.close()

    def put(self, content: bytes) -> BlobRef:
        """用不可预测文件名持久保存运行态内容。"""
        self._ensure_open()
        blob_id = secrets.token_hex(24)
        path = self._directory / blob_id
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return BlobRef(
            run_id=self._run_id,
            blob_id=blob_id,
            content_hash=hashlib.sha256(content).hexdigest(),
            content_length=len(content),
        )

    def get(self, reference: BlobRef) -> bytes:
        """读取同一 Run 内的 Blob 并校验 hash 与长度。"""
        self._ensure_open()
        if reference.run_id != self._run_id:
            raise BlobScopeError(
                expected_run_id=self._run_id,
                actual_run_id=reference.run_id,
            )
        try:
            content = (self._directory / reference.blob_id).read_bytes()
        except OSError as error:
            raise BlobIntegrityError(blob_id=reference.blob_id) from error
        valid_length = len(content) == reference.content_length
        valid_hash = hashlib.sha256(content).hexdigest() == reference.content_hash
        if not (valid_length and valid_hash):
            raise BlobIntegrityError(blob_id=reference.blob_id)
        return content

    def flush(self) -> None:
        """确认资源仍可用；每次 put 已单独 fsync。"""
        self._ensure_open()

    def close(self) -> None:
        """关闭逻辑资源；不删除任何 Blob。"""
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise StoreClosedError(resource="BlobStore")
