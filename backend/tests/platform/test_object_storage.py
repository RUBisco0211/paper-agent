"""两种存储实现必须表现一致：换后端不改业务代码。

同一组用例跑在本地文件系统与（moto 模拟的）S3 上；设 ``PAPER_AGENT_LIVE_STORAGE=1``
时再加一档，直接跑在配置指向的真实 S3 兼容服务（如本地 RustFS）上。
"""

import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from app.platform.config import settings
from app.platform.s3_storage import MULTIPART_THRESHOLD, S3ObjectStorage
from app.platform.storage import LocalObjectStorage, mineru_artifact_key, paper_pdf_key

BUCKET = "paper-agent-test"
LIVE = os.environ.get("PAPER_AGENT_LIVE_STORAGE") == "1"


@pytest.fixture(params=["local", "s3"] + (["s3-live"] if LIVE else []))
def storage(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "local":
        yield LocalObjectStorage(tmp_path / "storage")
        return
    if request.param == "s3-live":
        # 真实服务：桶名带后缀，避免和别的用途撞；用例自己清理写入的对象
        live = S3ObjectStorage(
            bucket=f"{settings.s3_bucket}-live-test",
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            addressing_style=settings.s3_addressing_style,
        )
        try:
            yield live
        finally:
            for prefix in ("papers/", "mineru/", "sessions/"):
                live.delete_prefix(prefix)
        return
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield S3ObjectStorage(
            bucket=BUCKET,
            endpoint_url="",
            access_key="test-key",
            secret_key="test-secret",
        )


def test_bucket_is_created_when_missing(tmp_path: Path) -> None:
    with mock_aws():
        storage = S3ObjectStorage(
            bucket="fresh-bucket",
            endpoint_url="",
            access_key="k",
            secret_key="s",
        )
        storage.put_bytes("a.txt", b"ok")
        assert storage.read_bytes("a.txt") == b"ok"


def test_put_read_and_delete_roundtrip(storage) -> None:
    key = paper_pdf_key("a" * 64)

    assert storage.exists(key) is False
    storage.put_bytes(key, b"%PDF-1.7 payload")
    assert storage.exists(key) is True
    assert storage.read_bytes(key) == b"%PDF-1.7 payload"

    storage.delete(key)
    assert storage.exists(key) is False


def test_read_text_roundtrip(storage) -> None:
    key = mineru_artifact_key("b" * 64, "content_list.json")

    storage.put_bytes(key, b'{"blocks": []}')
    assert storage.read_text(key) == '{"blocks": []}'


def test_missing_object_raises_file_not_found(storage) -> None:
    """两种实现的缺失语义必须一致，否则应用层要写两套分支。"""
    with pytest.raises(FileNotFoundError):
        storage.read_bytes("papers/ff/ff/missing.pdf")
    with pytest.raises(FileNotFoundError):
        storage.open("papers/ff/ff/missing.pdf")
    with (
        pytest.raises(FileNotFoundError),
        storage.materialize("papers/ff/ff/missing.pdf"),
    ):
        pass


def test_append_bytes_keeps_previous_content(storage) -> None:
    """会话 Entry 日志靠追加写入（一行一个 Entry）。"""
    key = "sessions/u1/s1.jsonl"

    storage.append_bytes(key, b'{"seq": 0}\n')
    storage.append_bytes(key, b'{"seq": 1}\n')

    assert storage.read_bytes(key) == b'{"seq": 0}\n{"seq": 1}\n'


def test_open_supports_line_iteration(storage) -> None:
    """EntryStore 逐行读日志：直接迭代（不进入 with）也必须按行。

    S3 的 StreamingBody 直接迭代是 1KB 分块，且 ``__enter__`` 交出的是底层流；
    这里两种用法都要覆盖，否则日志会被读成「多行合一」。
    """
    key = "sessions/u1/s2.jsonl"
    storage.put_bytes(key, b'{"seq": 0}\n{"seq": 1}\n')

    # EntryStore 的用法：不进入 with，直接迭代
    assert [line.strip() for line in storage.open(key)] == [
        b'{"seq": 0}',
        b'{"seq": 1}',
    ]

    with storage.open(key) as stream:
        assert [line.strip() for line in stream] == [
            b'{"seq": 0}',
            b'{"seq": 1}',
        ]

    # 单行也要能被 readline 正确切出来（跨分块边界时同理）
    storage.put_bytes(key, b'{"seq": 0}\n' * 400)
    with storage.open(key) as stream:
        assert len([line for line in stream if line.strip()]) == 400


def test_write_chunks_small_object(storage) -> None:
    key = paper_pdf_key("c" * 64)

    written = storage.write_chunks(key, [b"abc", b"", b"def"])

    assert written == 6
    assert storage.read_bytes(key) == b"abcdef"


def test_write_chunks_large_object_uses_multipart(storage) -> None:
    """超过阈值走分片上传，数据仍要完整且顺序正确。"""
    key = paper_pdf_key("d" * 64)
    head = b"A" * (MULTIPART_THRESHOLD + 1)
    tail = b"B" * (MULTIPART_THRESHOLD + 1)

    written = storage.write_chunks(key, [head, tail])

    assert written == len(head) + len(tail)
    assert storage.read_bytes(key) == head + tail


def test_materialize_yields_a_readable_file(storage) -> None:
    """MinerU 适配器需要一个真实文件路径。"""
    key = paper_pdf_key("e" * 64)
    storage.put_bytes(key, b"%PDF-1.7 mine")

    with storage.materialize(key) as path:
        assert path.is_file()
        assert path.read_bytes() == b"%PDF-1.7 mine"

    # 块结束后对象本身仍然存在（调用方只是借用了路径）
    assert storage.read_bytes(key) == b"%PDF-1.7 mine"


def test_s3_materialize_copies_to_a_temporary_file(storage) -> None:
    """S3 没有本地路径：下载到临时文件，退出即删除。"""
    if isinstance(storage, LocalObjectStorage):
        pytest.skip("本地实现是零拷贝，见 test_local_materialize_is_zero_copy")
    key = paper_pdf_key("9" * 64)
    storage.put_bytes(key, b"%PDF-1.7 staged")

    with storage.materialize(key) as path:
        borrowed = path
        assert path.read_bytes() == b"%PDF-1.7 staged"
        # 临时副本不在存储根目录里
        assert "/storage/" not in path.as_posix()

    assert borrowed.exists() is False


def test_local_materialize_is_zero_copy(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "storage")
    key = paper_pdf_key("8" * 64)
    storage.put_bytes(key, b"%PDF-1.7 local")

    with storage.materialize(key) as path:
        # 本地实现直接给出存储内的真实路径，不复制
        assert path == (tmp_path / "storage" / key)

    assert path.exists() is True


def test_delete_prefix_only_touches_that_subtree(storage) -> None:
    first = mineru_artifact_key("f" * 64, "content_list.json")
    second = mineru_artifact_key("f" * 64, "images/0.png")
    keep = mineru_artifact_key("1" * 64, "content_list.json")
    for key in (first, second, keep):
        storage.put_bytes(key, b"payload")

    removed = storage.delete_prefix("mineru/ff/ff/" + "f" * 64 + "/")

    assert removed == 2
    assert storage.exists(first) is False
    assert storage.exists(second) is False
    assert storage.exists(keep) is True


def test_delete_prefix_on_empty_prefix_is_a_noop(storage) -> None:
    assert storage.delete_prefix("mineru/aa/bb/" + "a" * 64 + "/") == 0
