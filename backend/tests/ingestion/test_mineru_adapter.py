"""适配器级别的回归测试（离线，用 MockTransport）。

这里覆盖两个真实踩到过的坑：
1. 配置里写了具体端点（…/api/v4/extract/task）时必须归一化成 base URL；
2. 预签名上传地址**不能**带 Content-Type，否则 OSS 报 SignatureDoesNotMatch。
"""

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from app.ingestion.mineru import MineruParser, _normalize_base_url
from app.platform.errors import AppError

UPLOAD_URL = "https://oss.test/upload/probe.pdf"
ZIP_URL = "https://oss.test/result.zip"


def _artifact_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "output/probe_content_list.json",
            json.dumps([{"type": "text", "text": "hello", "page_idx": 0}]),
        )
        archive.writestr("output/full.md", b"# hello")
    return buffer.getvalue()


def _transport(
    *,
    upload_status: int = 200,
    batch_code: int = 0,
    batch_message: str = "ok",
    states: list[str] | None = None,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    remaining = list(states or ["done"])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/file-urls/batch"):
            return httpx.Response(
                200,
                json={
                    "code": batch_code,
                    "msg": batch_message,
                    "data": {"batch_id": "batch-1", "file_urls": [UPLOAD_URL]},
                },
            )
        if str(request.url) == UPLOAD_URL:
            return httpx.Response(
                upload_status, text="<Error>SignatureDoesNotMatch</Error>"
            )
        if request.url.path.endswith("/extract-results/batch/batch-1"):
            state = remaining.pop(0) if remaining else "done"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "extract_result": [
                            {
                                "file_name": "probe.pdf",
                                "state": state,
                                "err_msg": "" if state == "done" else "boom",
                                "full_zip_url": ZIP_URL,
                            },
                        ],
                    },
                },
            )
        if str(request.url) == ZIP_URL:
            return httpx.Response(200, content=_artifact_zip())
        return httpx.Response(404, json={"code": 1, "msg": "not found"})

    return httpx.MockTransport(handler), seen


def _parser(transport: httpx.MockTransport, **kwargs) -> MineruParser:
    return MineruParser(
        base_url=kwargs.pop("base_url", "https://mineru.net"),
        api_key="test-token",
        http_client_factory=lambda: httpx.Client(transport=transport),
        poll_interval=0,
        **kwargs,
    )


def test_upload_never_sends_content_type(tmp_path: Path) -> None:
    transport, seen = _transport()
    pdf = tmp_path / "probe.pdf"
    pdf.write_bytes(b"%PDF-1.7 minimal")

    artifact = _parser(transport).parse(pdf_path=pdf)

    upload = next(request for request in seen if str(request.url) == UPLOAD_URL)
    assert "content-type" not in {key.lower() for key in upload.headers}
    assert artifact.content_list[0]["text"] == "hello"
    assert artifact.markdown == "# hello"


def test_upload_url_is_normalized_to_the_base_url(tmp_path: Path) -> None:
    """配置里带端点路径也能工作（否则会拼出不存在的地址）。"""
    transport, seen = _transport()
    pdf = tmp_path / "probe.pdf"
    pdf.write_bytes(b"%PDF-1.7 minimal")

    _parser(transport, base_url="https://mineru.net/api/v4/extract/task").parse(
        pdf_path=pdf
    )

    requested = str(seen[0].url)
    assert requested == "https://mineru.net/api/v4/file-urls/batch"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://mineru.net", "https://mineru.net"),
        ("https://mineru.net/", "https://mineru.net"),
        ("https://mineru.net/api/v4/extract/task", "https://mineru.net"),
        ("https://host/mineru", "https://host/mineru"),
        ("", ""),
    ],
)
def test_normalize_base_url(value: str, expected: str) -> None:
    assert _normalize_base_url(value) == expected


def test_provider_error_carries_the_service_message(tmp_path: Path) -> None:
    transport, _ = _transport(batch_code=10001, batch_message="user token is invalid")
    pdf = tmp_path / "probe.pdf"
    pdf.write_bytes(b"%PDF-1.7 minimal")

    with pytest.raises(AppError) as excinfo:
        _parser(transport).parse(pdf_path=pdf)

    assert excinfo.value.code == "provider_not_configured"
    assert "user token is invalid" in excinfo.value.message


def test_rejected_upload_reports_the_oss_error(tmp_path: Path) -> None:
    transport, _ = _transport(upload_status=403)
    pdf = tmp_path / "probe.pdf"
    pdf.write_bytes(b"%PDF-1.7 minimal")

    with pytest.raises(AppError) as excinfo:
        _parser(transport).parse(pdf_path=pdf)

    assert excinfo.value.code == "provider_unavailable"
    assert "SignatureDoesNotMatch" in excinfo.value.message


def test_stuck_waiting_file_times_out(tmp_path: Path) -> None:
    transport, _ = _transport(states=["waiting-file"] * 12)
    pdf = tmp_path / "probe.pdf"
    pdf.write_bytes(b"%PDF-1.7 minimal")

    with pytest.raises(AppError) as excinfo:
        _parser(transport).parse(pdf_path=pdf)

    assert excinfo.value.code == "provider_unavailable"
    assert "未收到上传的文件" in excinfo.value.message


def test_failed_state_surfaces_the_provider_message(tmp_path: Path) -> None:
    transport, _ = _transport(states=["failed"])
    pdf = tmp_path / "probe.pdf"
    pdf.write_bytes(b"%PDF-1.7 minimal")

    with pytest.raises(AppError) as excinfo:
        _parser(transport).parse(pdf_path=pdf)

    assert excinfo.value.code == "ingestion_stage_failed"
    assert "boom" in excinfo.value.message
