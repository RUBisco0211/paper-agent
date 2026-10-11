"""Identifier resolution and online metadata completion."""

from app.literature_support.scholar.identifiers import (
    Identifier,
    IdentifierType,
    parse_identifier,
)
from app.literature_support.scholar.metadata import (
    MetadataResolver,
    ProviderMetadata,
    ResolutionOutcome,
    build_default_resolver,
)

__all__ = [
    "Identifier",
    "IdentifierType",
    "MetadataResolver",
    "ProviderMetadata",
    "ResolutionOutcome",
    "build_default_resolver",
    "parse_identifier",
]
