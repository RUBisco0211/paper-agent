"""Object storage boundary for PDFs, MinerU artifacts and session entry logs.

The MVP runs on a single machine, so the default implementation writes to a
local directory. Keys are always produced by helpers in this module; a future
S3/MinIO implementation only has to satisfy :class:`ObjectStorage`.
"""

import os
from collections.abc import Iterable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated, BinaryIO, Protocol

from fastapi import Depends

from .config import settings
from .errors import AppError, ErrorCode


def paper_pdf_key(file_hash: str) -> str:
    return f"papers/{file_hash[0:2]}/{file_hash[2:4]}/{file_hash}.pdf"


def mineru_artifact_key(file_hash: str, relative_path: str) -> str:
    return f"mineru/{file_hash[0:2]}/{file_hash[2:4]}/{file_hash}/{relative_path}"


def mineru_artifact_prefix(file_hash: str) -> str:
    return f"mineru/{file_hash[0:2]}/{file_hash[2:4]}/{file_hash}/"


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

    def local_path(self, key: str) -> Path: ...


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

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)

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

    def local_path(self, key: str) -> Path:
        return self._resolve(key)

    def files(self, prefix: str) -> Iterator[str]:
        directory = self._resolve(prefix)
        if not directory.exists():
            return
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                yield path.relative_to(self._root).as_posix()

    def write_chunks(self, key: str, chunks: Iterable[bytes]) -> int:
        """Stream an iterable into a new object and return the byte count."""
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        size = 0
        try:
            with temporary.open("wb") as handle:
                for chunk in chunks:
                    handle.write(chunk)
                    size += len(chunk)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        os.replace(temporary, path)
        return size


@lru_cache
def get_object_storage() -> ObjectStorage:
    return LocalObjectStorage(settings.storage_root)


StorageDep = Annotated[ObjectStorage, Depends(get_object_storage)]
