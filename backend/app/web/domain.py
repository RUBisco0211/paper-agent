"""Public web reads as a user-facing capability, independent of a provider."""


class WebProviderError(Exception):
    """Base class for the failures a web provider can report."""


class ProviderRateLimited(WebProviderError):
    """The provider asked us to slow down."""


class ProviderQuotaExhausted(WebProviderError):
    """The user's plan or pay-as-you-go limit is used up."""


class InvalidCredential(WebProviderError):
    """The provider rejected the API key."""


class ProviderUnavailable(WebProviderError):
    """Timeout, transport failure, or provider-side error."""


class WebPageNotFound(WebProviderError):
    """The provider could not extract the requested page."""


DEFAULT_MAX_CHARS = 8000
MAX_MAX_CHARS = 20000


def window_page(url: str, content: str, start: int, size: int) -> dict:
    """Return one slice of a page plus the offset that continues it."""
    if start >= len(content):
        return {
            "status": "ok",
            "url": url,
            "content": "",
            "truncated": False,
            "next_offset": None,
            "total_chars": len(content),
            "offset_out_of_range": True,
        }
    end = start + size
    truncated = end < len(content)
    return {
        "status": "ok",
        "url": url,
        "content": content[start:end],
        "truncated": truncated,
        "next_offset": end if truncated else None,
        "total_chars": len(content),
        "offset_out_of_range": False,
    }


def search_envelope(provider: str, results: list[dict]) -> dict:
    """Shape returned to the agent for a completed search."""
    return {"status": "ok", "provider": provider, "results": results}
