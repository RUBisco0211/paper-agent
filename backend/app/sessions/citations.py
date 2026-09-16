"""Stable identifiers for evidence-backed citations.

A citation id is derived from the chunks it points at, so the same evidence
resolves to the same id without a global counter, and the model can only refer
to ids that the backend actually stored.
"""

import hashlib
from uuid import UUID


def build_citation_id(chunk_ids: list[UUID]) -> str:
    """Deterministic id for one piece of evidence."""
    if not chunk_ids:
        raise ValueError("引用必须至少包含一个 chunk")
    payload = ":".join(sorted(str(chunk_id) for chunk_id in chunk_ids))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"cit_{digest}"
