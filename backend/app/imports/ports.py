"""Ports the import module needs from its environment."""

from typing import Protocol


class PdfSourceLocator(Protocol):
    def find(self, doi: str) -> list[str]: ...


class PaperDiscoveryAdapter(Protocol):
    def search(self, query: str, limit: int) -> "PaperDiscoveryResult": ...


class PaperDiscoveryResult(Protocol):
    papers: list[dict]
    failed_sources: list[str]
