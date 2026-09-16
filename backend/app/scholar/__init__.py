"""Identifier resolution and online metadata completion."""

from .identifiers import Identifier, IdentifierType, parse_identifier
from .metadata import (
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
