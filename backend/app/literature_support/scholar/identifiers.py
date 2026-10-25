"""Normalization of user-supplied paper identifiers.

Only DOI and arXiv are supported in the first version; free-text title search
and arbitrary URL crawling are deliberately out of scope.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.platform.errors import AppError, ErrorCode

DOI_PREFIX = "10."
ARXIV_MODERN = re.compile(r"^(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?$")
ARXIV_LEGACY = re.compile(
    r"^(?P<id>[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?P<version>v\d+)?$",
)
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")
ARXIV_DOI = re.compile(
    r"^10\.48550/arxiv\.(?P<id>\d{4}\.\d{4,5})(?:v\d+)?$", re.IGNORECASE
)
_TRAILING_PUNCTUATION = ".,;)\"'"


class IdentifierType(StrEnum):
    DOI = "doi"
    ARXIV = "arxiv"


@dataclass(frozen=True, slots=True)
class Identifier:
    type: IdentifierType
    value: str
    version: str | None = None

    @property
    def full_value(self) -> str:
        """The identifier as it was given, version included.

        An arXiv id with a version names exactly one file, so the version must
        survive into storage; without a version it means "the latest".
        """
        if self.type is IdentifierType.ARXIV and self.version:
            return f"{self.value}{self.version}"
        return self.value

    @property
    def canonical_url(self) -> str:
        if self.type is IdentifierType.DOI:
            return f"https://doi.org/{self.value}"
        return f"https://arxiv.org/abs/{self.full_value}"


def parse_identifier(text: str) -> Identifier:
    """Normalize a DOI, arXiv id or canonical link into an identifier."""
    candidate = (text or "").strip()
    if not candidate:
        raise _invalid()

    lowered = candidate.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/"):
        if lowered.startswith(prefix):
            return _doi(candidate[len(prefix) :])

    for prefix in ("doi:", "https://arxiv.org/abs/", "arxiv:", "http://arxiv.org/abs/"):
        if lowered.startswith(prefix):
            remainder = candidate[len(prefix) :]
            if prefix.startswith("doi"):
                return _doi(remainder)
            return _arxiv(remainder)

    if lowered.startswith("https://arxiv.org/pdf/") or lowered.startswith(
        "http://arxiv.org/pdf/",
    ):
        remainder = candidate.split("/pdf/", 1)[1]
        return _arxiv(remainder)

    if candidate.startswith(DOI_PREFIX):
        return _doi(candidate)
    return _arxiv(candidate)


DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/[^\s\"'<>()\[\]]+")
ARXIV_IN_TEXT = re.compile(r"(?:arXiv[:\s]*)(\d{4}\.\d{4,5}(?:v\d+)?)")


def find_identifiers(text: str, *, limit: int = 4) -> list[Identifier]:
    """Best-effort identifier detection inside free text (PDF front matter).

    Used for local recognition only: a detected identifier still has to be
    confirmed by an exact online lookup before it is trusted.
    """
    found: list[Identifier] = []
    seen: set[tuple[IdentifierType, str]] = set()

    def _add(identifier: Identifier) -> None:
        key = (identifier.type, identifier.value)
        if key not in seen and len(found) < limit:
            seen.add(key)
            found.append(identifier)

    for match in DOI_IN_TEXT.finditer(text):
        try:
            _add(_doi(match.group(0)))
        except AppError:
            continue
    for match in ARXIV_IN_TEXT.finditer(text):
        try:
            _add(_arxiv(match.group(1)))
        except AppError:
            continue
    return found


def _doi(value: str) -> Identifier:
    normalized = value.strip().rstrip(_TRAILING_PUNCTUATION)
    if not DOI_PATTERN.match(normalized):
        raise _invalid()
    if match := ARXIV_DOI.fullmatch(normalized):
        return _arxiv(match.group("id"))
    return Identifier(type=IdentifierType.DOI, value=normalized)


def _arxiv(value: str) -> Identifier:
    normalized = value.strip().rstrip(_TRAILING_PUNCTUATION)
    for suffix in (".pdf",):
        if normalized.lower().endswith(suffix):
            normalized = normalized[: -len(suffix)]
    for pattern in (ARXIV_MODERN, ARXIV_LEGACY):
        if match := pattern.match(normalized):
            return Identifier(
                type=IdentifierType.ARXIV,
                value=match.group("id"),
                version=match.group("version"),
            )
    raise _invalid()


def _invalid() -> AppError:
    return AppError(
        "只支持 DOI 或 arXiv 标识符及其规范链接",
        code=ErrorCode.IDENTIFIER_INVALID,
        status_code=422,
    )
