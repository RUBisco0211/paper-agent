import io
import json
import zipfile

import pytest

from app.literature_support.processing.mineru import _read_artifact
from app.platform.errors import AppError


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_reads_nested_content_list_markdown_and_images() -> None:
    payload = _zip(
        {
            "output/paper_content_list.json": json.dumps(
                [{"type": "text", "text": "hello", "page_idx": 0}],
            ).encode(),
            "output/full.md": b"# Hello",
            "output/images/figure-1.png": b"\x89PNG-bytes",
            "output/version.json": b'{"version": "2.1.0"}',
        },
    )

    artifact = _read_artifact(payload)

    assert artifact.content_list == [{"type": "text", "text": "hello", "page_idx": 0}]
    assert artifact.markdown == "# Hello"
    assert artifact.images == {"output/images/figure-1.png": b"\x89PNG-bytes"}
    assert artifact.version == '{"version": "2.1.0"}'


def test_missing_content_list_is_rejected() -> None:
    payload = _zip({"full.md": b"# Hello"})

    with pytest.raises(AppError) as excinfo:
        _read_artifact(payload)

    assert excinfo.value.code == "ingestion_artifact_invalid"


def test_path_traversal_is_rejected() -> None:
    payload = _zip({"../escape.json": b"{}", "content_list.json": b"[]"})

    with pytest.raises(AppError) as excinfo:
        _read_artifact(payload)

    assert excinfo.value.code == "ingestion_artifact_invalid"


def test_incompatible_json_is_rejected() -> None:
    not_json = _zip({"content_list.json": b"not json"})
    not_a_list = _zip({"content_list.json": b'{"blocks": []}'})
    empty = _zip({"content_list.json": b"[]"})

    for payload in (not_json, not_a_list, empty):
        with pytest.raises(AppError) as excinfo:
            _read_artifact(payload)
        assert excinfo.value.code == "ingestion_artifact_invalid"


def test_invalid_zip_is_rejected() -> None:
    with pytest.raises(AppError) as excinfo:
        _read_artifact(b"definitely not a zip")

    assert excinfo.value.code == "ingestion_artifact_invalid"
