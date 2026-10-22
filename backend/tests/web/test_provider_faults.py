"""An unexpected provider fault stays inside the error contract."""

from uuid import uuid4

import pytest

from app.platform.errors import ProviderUnavailableError
from app.web.service import WebSearchService


class DictCredentials:
    def secret(self, user_id, kind: str, field: str) -> str | None:
        return "tvly"


class DictStore:
    def get(self, user_id: str, url: str) -> str | None:
        return None

    def put(self, user_id: str, url: str, content: str) -> None:
        return None


class FaultyProvider:
    """Raises something no branch of ``_translate`` knows about."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def search(self, query: str, max_results: int) -> list[dict]:
        raise self.error

    def extract(self, url: str) -> str:
        raise self.error

    def extract_excerpt(self, url: str, query: str, chunks: int) -> str:
        raise self.error


def _service(error: Exception) -> WebSearchService:
    return WebSearchService(
        DictCredentials(), DictStore(), lambda key: FaultyProvider(error)
    )


@pytest.mark.parametrize(
    "fault",
    [
        RuntimeError("credential_decryption_failed"),
        KeyError("raw_content"),
        AttributeError("missing"),
    ],
)
def test_an_unexpected_fault_is_reported_as_unavailable_not_a_server_error(fault):
    with pytest.raises(ProviderUnavailableError) as caught:
        _service(fault).search(uuid4(), "query", 5)

    failure = caught.value
    assert str(failure.code) == "provider_unavailable"
    assert failure.details == {"error": type(fault).__name__}


def test_an_unexpected_fault_on_a_read_is_also_translated():
    with pytest.raises(ProviderUnavailableError) as caught:
        _service(RuntimeError("boom")).fetch(uuid4(), "https://a", 0, 100)

    assert str(caught.value.code) == "provider_unavailable"
