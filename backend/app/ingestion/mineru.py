"""MinerU adapter for the full-text parsing stage.

The batch flow mirrors MinerU's hosted API: request an upload URL, PUT the PDF,
poll the batch until it is done, then download and validate the result ZIP. All
outputs are treated as untrusted: names are checked for traversal, sizes are
bounded and the required ``content_list.json`` is validated before use.
"""

import io
import time
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import structlog

from ..platform.errors import AppError, ErrorCode
from ..scholar.metadata import HttpClientFactory, default_http_client_factory

logger = structlog.get_logger(__name__)

UPLOAD_URL_PATH = "/api/v4/file-urls/batch"
BATCH_RESULT_PATH = "/api/v4/extract-results/batch/{batch_id}"

MAX_ZIP_BYTES = 256 * 1024 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 128 * 1024 * 1024
POLL_INTERVAL_SECONDS = 3.0
SUCCESS_STATES = {"done", "success", "succeeded", "finished"}
FAILURE_STATES = {"failed", "error"}


@dataclass(frozen=True, slots=True)
class MineruArtifact:
    """Validated MinerU output for one paper."""

    content_list: list[dict]
    markdown: str | None
    images: dict[str, bytes] = field(default_factory=dict)
    version: str | None = None


class MineruParser:
    """Hosted MinerU client; disabled until the instance configures it."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 600.0,
        http_client_factory: HttpClientFactory = default_http_client_factory,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client_factory = http_client_factory
        self._poll_interval = poll_interval

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url)

    def parse(self, *, pdf_path: Path) -> MineruArtifact:
        if not self.is_configured:
            raise AppError(
                "MinerU 未配置",
                code=ErrorCode.PROVIDER_NOT_CONFIGURED,
                status_code=503,
            )

        with self._client_factory() as client:
            batch_id, upload_url = self._request_upload_url(client, pdf_path)
            self._upload(client, upload_url, pdf_path)
            zip_bytes = self._await_result(client, batch_id)

        return _read_artifact(zip_bytes)

    # Protocol steps --------------------------------------------------------
    def _request_upload_url(
        self,
        client: httpx.Client,
        pdf_path: Path,
    ) -> tuple[str, str]:
        payload = {
            "enable_formula": True,
            "language": "en",
            "files": [{"name": pdf_path.name, "is_ocr": False}],
        }
        response = self._post(
            client, f"{self._base_url}{UPLOAD_URL_PATH}", json=payload
        )
        data = _data_of(response)
        batch_id = data.get("batch_id")
        urls = data.get("file_urls") or []
        if not batch_id or not urls:
            raise _invalid_artifact("MinerU 没有返回上传地址")
        return str(batch_id), str(urls[0])

    def _upload(self, client: httpx.Client, upload_url: str, pdf_path: Path) -> None:
        try:
            with pdf_path.open("rb") as handle:
                response = client.put(
                    upload_url,
                    content=handle.read(),
                    headers={"Content-Type": "application/pdf"},
                )
        except httpx.HTTPError as exc:
            raise _provider_unavailable("上传 PDF 到 MinerU 失败") from exc
        if response.status_code >= 400:
            raise _provider_unavailable("MinerU 拒绝了 PDF 上传")

    def _await_result(self, client: httpx.Client, batch_id: str) -> bytes:
        deadline = time.monotonic() + self._timeout_seconds
        url = f"{self._base_url}{BATCH_RESULT_PATH.format(batch_id=batch_id)}"
        while True:
            response = self._get(client, url)
            result = _first_result(response)
            state = str(result.get("state", "")).lower()
            if state in SUCCESS_STATES:
                zip_url = result.get("full_zip_url") or result.get("zip_url")
                if not zip_url:
                    raise _invalid_artifact("MinerU 完成但未返回结果压缩包")
                return self._download_zip(client, str(zip_url))
            if state in FAILURE_STATES:
                raise AppError(
                    f"MinerU 解析失败：{result.get('err_msg') or state}",
                    code=ErrorCode.INGESTION_STAGE_FAILED,
                    status_code=502,
                )
            if time.monotonic() >= deadline:
                raise AppError(
                    "等待 MinerU 解析超时",
                    code=ErrorCode.PROVIDER_UNAVAILABLE,
                    status_code=504,
                )
            time.sleep(self._poll_interval)

    def _download_zip(self, client: httpx.Client, zip_url: str) -> bytes:
        try:
            with client.stream("GET", zip_url) as response:
                if response.status_code >= 400:
                    raise _provider_unavailable("下载 MinerU 结果失败")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_ZIP_BYTES:
                        raise _invalid_artifact("MinerU 结果压缩包超过大小上限")
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise _provider_unavailable("下载 MinerU 结果失败") from exc
        return b"".join(chunks)

    # HTTP helpers ----------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _post(self, client: httpx.Client, url: str, *, json: dict) -> httpx.Response:
        try:
            response = client.post(url, json=json, headers=self._headers())
        except httpx.HTTPError as exc:
            raise _provider_unavailable("无法连接 MinerU") from exc
        return _check(response)

    def _get(self, client: httpx.Client, url: str) -> httpx.Response:
        try:
            response = client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise _provider_unavailable("无法连接 MinerU") from exc
        return _check(response)


def _check(response: httpx.Response) -> httpx.Response:
    if response.status_code in {401, 403}:
        raise AppError(
            "MinerU 鉴权失败",
            code=ErrorCode.PROVIDER_NOT_CONFIGURED,
            status_code=503,
        )
    if response.status_code == 429:
        raise AppError(
            "MinerU 限流",
            code=ErrorCode.PROVIDER_RATE_LIMITED,
            status_code=429,
        )
    if response.status_code >= 400:
        raise _provider_unavailable(f"MinerU 返回 {response.status_code}")
    return response


def _data_of(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise _invalid_artifact("MinerU 返回内容不是 JSON") from exc
    if not isinstance(payload, dict):
        raise _invalid_artifact("MinerU 返回结构不兼容")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise _invalid_artifact(f"MinerU 返回缺少 data：{payload.get('msg') or ''}")
    return data


def _first_result(response: httpx.Response) -> dict:
    results = _data_of(response).get("extract_result") or []
    if not results or not isinstance(results[0], dict):
        raise _invalid_artifact("MinerU 返回缺少解析结果")
    return results[0]


def _read_artifact(zip_bytes: bytes) -> MineruArtifact:
    """Validate the ZIP and load its JSON, Markdown and images."""
    content_list: list[dict] | None = None
    markdown: str | None = None
    images: dict[str, bytes] = {}
    image_bytes = 0
    version: str | None = None

    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise _invalid_artifact("MinerU 结果不是有效的压缩包") from exc

    with archive:
        for name in _safe_names(archive.namelist()):
            info = archive.getinfo(name)
            lowered = name.lower()
            if lowered.endswith("content_list.json"):
                if info.file_size > MAX_JSON_BYTES:
                    raise _invalid_artifact("content_list.json 超过大小上限")
                content_list = _load_content_list(archive.read(name))
            elif lowered.endswith("version.json"):
                version = archive.read(name).decode("utf-8", errors="ignore")[:128]
            elif lowered.endswith((".md", "full.md")):
                if markdown is None:
                    markdown = archive.read(name).decode("utf-8", errors="ignore")
            elif lowered.endswith((".png", ".jpg", ".jpeg", ".webp")):
                if info.file_size > MAX_IMAGE_BYTES:
                    raise _invalid_artifact(f"图片 {name} 超过大小上限")
                image_bytes += info.file_size
                if image_bytes > MAX_TOTAL_IMAGE_BYTES:
                    raise _invalid_artifact("MinerU 图片总量超过上限")
                images[name] = archive.read(name)

    if content_list is None:
        raise _invalid_artifact("MinerU 结果缺少 content_list.json")
    return MineruArtifact(
        content_list=content_list,
        markdown=markdown,
        images=images,
        version=version,
    )


def _safe_names(names: list[str]) -> Iterator[str]:
    for name in names:
        if name.startswith("/") or ".." in Path(name).parts:
            raise _invalid_artifact(f"MinerU 结果包含不安全路径：{name}")
        if name.endswith("/"):
            continue
        yield name


def _load_content_list(payload: bytes) -> list[dict]:
    import json

    try:
        parsed = json.loads(payload)
    except ValueError as exc:
        raise _invalid_artifact("content_list.json 不是合法 JSON") from exc
    if not isinstance(parsed, list) or not parsed:
        raise _invalid_artifact("content_list.json 结构不兼容")
    if not any(isinstance(block, dict) for block in parsed):
        raise _invalid_artifact("content_list.json 缺少有效块")
    return [block for block in parsed if isinstance(block, dict)]


def _provider_unavailable(message: str) -> AppError:
    return AppError(
        message,
        code=ErrorCode.PROVIDER_UNAVAILABLE,
        status_code=502,
    )


def _invalid_artifact(message: str) -> AppError:
    return AppError(
        message,
        code=ErrorCode.INGESTION_ARTIFACT_INVALID,
        status_code=502,
    )
