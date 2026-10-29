"""S3-compatible object storage (RustFS, Garage, Aliyun OSS, R2, ...).

Enabled with ``STORAGE_BACKEND=s3``. Self-hosted services such as RustFS only
serve path-style requests, so the client is configured accordingly by default.
"""

import io
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import BinaryIO, NoReturn

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from .errors import AppError, ErrorCode

#: 分片上传的阈值与片大小：PDF 可能到几十 MB，避免整份读进内存
PART_SIZE = 8 * 1024 * 1024
MULTIPART_THRESHOLD = PART_SIZE
#: S3 单次批量删除的上限
DELETE_BATCH = 1000


class S3ObjectStorage:
    """Object storage backed by any S3-compatible endpoint."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        addressing_style: str = "path",
        create_bucket: bool = True,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region,
            config=BotoConfig(
                s3={"addressing_style": addressing_style},
                # botocore defaults to 10 pooled connections per client. The
                # API thread pool alone can issue more than that, and a full
                # pool discards connections instead of waiting, so raise it.
                max_pool_connections=32,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        if create_bucket:
            self._ensure_bucket()

    # -- 内部 ---------------------------------------------------------------

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            if _status_of(exc) not in {403, 404}:
                raise _storage_error(exc) from exc
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except (ClientError, BotoCoreError) as create_error:
                raise _storage_error(create_error) from create_error

    def _object(self, key: str):
        return self._client.get_object(Bucket=self._bucket, Key=key)

    # -- ObjectStorage 协议 -------------------------------------------------

    def put_bytes(self, key: str, data: bytes) -> None:
        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        except (ClientError, BotoCoreError) as exc:
            raise _storage_error(exc) from exc

    def read_bytes(self, key: str) -> bytes:
        try:
            return self._object(key)["Body"].read()
        except (ClientError, BotoCoreError) as exc:
            _raise_storage_error(exc, key)

    def read_text(self, key: str) -> str:
        return self.read_bytes(key).decode("utf-8")

    def append_bytes(self, key: str, data: bytes) -> None:
        """对象存储没有追加语义：读回、拼接、写回。

        仅用于会话 Entry 日志（一行一个 Entry，量级很小）。
        """
        existing = self.read_bytes(key) if self.exists(key) else b""
        self.put_bytes(key, existing + data)

    def write_chunks(self, key: str, chunks: Iterable[bytes]) -> int:
        """流式写入：超过阈值走分片上传，中途失败会终止分片。"""
        buffer = bytearray()
        size = 0
        upload_id: str | None = None
        parts: list[dict] = []
        part_number = 1
        try:
            for chunk in chunks:
                if not chunk:
                    continue
                buffer.extend(chunk)
                size += len(chunk)
                if len(buffer) < PART_SIZE:
                    continue
                if upload_id is None:
                    upload_id = self._begin_multipart(key)
                parts.append(
                    self._upload_part(key, upload_id, part_number, bytes(buffer))
                )
                part_number += 1
                buffer.clear()

            if upload_id is None:
                # 小文件：一次写入即可，不必分片
                self.put_bytes(key, bytes(buffer))
                return size

            if buffer:
                parts.append(
                    self._upload_part(key, upload_id, part_number, bytes(buffer)),
                )
            self._complete_multipart(key, upload_id, parts)
        except (ClientError, BotoCoreError) as exc:
            if upload_id is not None:
                self._abort_quietly(key, upload_id)
            raise _storage_error(exc) from exc
        except BaseException:
            if upload_id is not None:
                self._abort_quietly(key, upload_id)
            raise
        return size

    def _begin_multipart(self, key: str) -> str:
        response = self._client.create_multipart_upload(Bucket=self._bucket, Key=key)
        return str(response["UploadId"])

    def _upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        body: bytes,
    ) -> dict:
        response = self._client.upload_part(
            Bucket=self._bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=body,
        )
        return {"ETag": response["ETag"], "PartNumber": part_number}

    def _complete_multipart(self, key: str, upload_id: str, parts: list[dict]) -> None:
        self._client.complete_multipart_upload(
            Bucket=self._bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

    def _abort_quietly(self, key: str, upload_id: str) -> None:
        with suppress(ClientError, BotoCoreError):  # 尽力而为，失败不影响主错误
            self._client.abort_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
            )

    def open(self, key: str) -> BinaryIO:
        """返回与本地实现一致的可读文件对象（迭代按行）。

        botocore 的 StreamingBody 直接迭代是 **1KB 分块**，而且它的 ``__enter__``
        会把底层流交出去——两者都会让按行读取（会话 Entry 日志）读到半行或整段。
        包一层 BufferedReader 后语义与本地 ``open()`` 完全相同。
        """
        try:
            return io.BufferedReader(self._object(key)["Body"])  # type: ignore[arg-type]
        except (ClientError, BotoCoreError) as exc:
            _raise_storage_error(exc, key)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _status_of(exc) == 404:
                return False
            raise _storage_error(exc) from exc
        except BotoCoreError as exc:
            raise _storage_error(exc) from exc
        return True

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            raise _storage_error(exc) from exc

    def delete_prefix(self, prefix: str) -> int:
        removed = 0
        for keys in self._list_keys(prefix):
            try:
                self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
                )
            except (ClientError, BotoCoreError) as exc:
                raise _storage_error(exc) from exc
            removed += len(keys)
        return removed

    def _list_keys(self, prefix: str) -> Iterator[list[str]]:
        paginator = self._client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                keys = [item["Key"] for item in page.get("Contents", [])]
                while keys:
                    batch, keys = keys[:DELETE_BATCH], keys[DELETE_BATCH:]
                    yield batch
        except (ClientError, BotoCoreError) as exc:
            raise _storage_error(exc) from exc

    def files(self, prefix: str) -> Iterator[str]:
        for page in self._list_keys(prefix):
            yield from page

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]:
        """下载到临时文件：MinerU 适配器需要一个真实路径。

        退出时删除临时文件，调用方不能保留这个路径。
        """
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            path = Path(handle.name)
            try:
                for chunk in self._object(key)["Body"].iter_chunks():
                    handle.write(chunk)
            except (ClientError, BotoCoreError) as exc:
                _raise_storage_error(exc, key)
        try:
            yield path
        except (ClientError, BotoCoreError) as exc:
            raise _storage_error(exc) from exc
        finally:
            path.unlink(missing_ok=True)


def _status_of(exc: Exception) -> int | None:
    response = getattr(exc, "response", None) or {}
    return (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")


def _is_missing(exc: Exception) -> bool:
    code = (getattr(exc, "response", None) or {}).get("Error", {}).get("Code", "")
    return _status_of(exc) == 404 or code in {"NoSuchKey", "NoSuchBucket", "404"}


def _storage_error(exc: Exception) -> AppError:
    """把 boto 的错误折成稳定错误码，避免把服务商细节泄露给客户端。"""
    return AppError(
        "对象存储不可用",
        status_code=503,
        code=ErrorCode.PROVIDER_UNAVAILABLE,
    )


def _raise_storage_error(exc: Exception, key: str) -> NoReturn:
    """缺失对象与本地实现保持同一语义（FileNotFoundError）。

    对象存储服务本身不可用是另一回事：那是 503，由应用层决定怎么呈现。
    """
    if _is_missing(exc):
        raise FileNotFoundError(key) from exc
    raise _storage_error(exc) from exc
