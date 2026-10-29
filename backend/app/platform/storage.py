"""Object storage boundary for PDFs, MinerU artifacts and session entry logs.

Two interchangeable implementations satisfy :class:`ObjectStorage`:

- :class:`LocalObjectStorage` (default) writes to ``STORAGE_ROOT``; suited to a
  single-machine deployment with a mounted volume.
- :class:`S3ObjectStorage` talks to any S3-compatible service (RustFS, Garage,
  Aliyun OSS, Cloudflare R2 ...); needed once several instances share data.

Keys are always produced by the helpers in this module, so switching backends is
a configuration change. Anything that needs a real file on disk (the MinerU
adapter uploads a file) goes through :meth:`ObjectStorage.materialize`.
"""

import os
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated, BinaryIO, Protocol, cast

from fastapi import Depends

from .config import settings
from .errors import AppError, ErrorCode


def paper_pdf_key(file_hash: str) -> str:
    return f"papers/{file_hash[0:2]}/{file_hash[2:4]}/{file_hash}.pdf"


def mineru_artifact_key(file_hash: str, relative_path: str) -> str:
    return f"mineru/{file_hash[0:2]}/{file_hash[2:4]}/{file_hash}/{relative_path}"


def session_entries_key(user_id: str, session_id: str) -> str:
    return f"sessions/{user_id}/{session_id}.jsonl"


class ObjectStorage(Protocol):
    def put_bytes(self, key: str, data: bytes) -> None: ...

    def read_bytes(self, key: str) -> bytes: ...

    def read_text(self, key: str) -> str: ...

    def append_bytes(self, key: str, data: bytes) -> None: ...

    def write_chunks(self, key: str, chunks: Iterable[bytes]) -> int: ...

    def open(self, key: str) -> BinaryIO: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def delete_prefix(self, prefix: str) -> int: ...

    def materialize(self, key: str) -> AbstractContextManager[Path]: ...


class LocalObjectStorage:
    """Filesystem-backed object storage rooted at ``settings.storage_root``."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        normalized = key.strip("/")
        if (
            not normalized
            or normalized.startswith("..")
            or ".." in normalized.split("/")
        ):
            raise AppError("非法对象存储 Key", code=ErrorCode.VALIDATION_ERROR)
        candidate = (self._root / normalized).resolve()
        if not candidate.is_relative_to(self._root):
            raise AppError("非法对象存储 Key", code=ErrorCode.VALIDATION_ERROR)
        return candidate

    @contextmanager
    def _atomic_file(self, key: str) -> Iterator[BinaryIO]:
        """Write to a sibling temp file, then replace the target atomically."""
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            try:
                yield cast(BinaryIO, handle)
                handle.flush()
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def put_bytes(self, key: str, data: bytes) -> None:
        with self._atomic_file(key) as handle:
            handle.write(data)

    def read_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def read_text(self, key: str) -> str:
        return self._resolve(key).read_text(encoding="utf-8")

    def append_bytes(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(data)

    def open(self, key: str) -> BinaryIO:
        return self._resolve(key).open("rb")

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> int:
        directory = self._resolve(prefix)
        if not directory.exists():
            return 0
        removed = 0
        for path in sorted(directory.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
                removed += 1
            else:
                path.rmdir()
        directory.rmdir()
        return removed

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]:
        """本地实现零拷贝：直接给出存储内的真实路径（不会复制，也不会删除）。"""
        path = self._resolve(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        yield path

    def files(self, prefix: str) -> Iterator[str]:
        directory = self._resolve(prefix)
        if not directory.exists():
            return
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                yield path.relative_to(self._root).as_posix()

    def write_chunks(self, key: str, chunks: Iterable[bytes]) -> int:
        """Stream an iterable into a new object and return the byte count."""
        size = 0
        with self._atomic_file(key) as handle:
            for chunk in chunks:
                handle.write(chunk)
                size += len(chunk)
        return size


@lru_cache
def get_object_storage() -> ObjectStorage:
    if settings.storage_backend == "s3":
        # 延迟导入：不用 S3 时不需要装 boto3 的调用路径
        from .s3_storage import S3ObjectStorage

        return S3ObjectStorage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            addressing_style=settings.s3_addressing_style,
        )
    return LocalObjectStorage(settings.storage_root)


StorageDep = Annotated[ObjectStorage, Depends(get_object_storage)]
