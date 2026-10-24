"""Validate positional identity and pgvector-compatible numeric range."""

import struct

import httpx
import pytest
from sqlalchemy import text

from app.literature_support.embedding import OpenAICompatibleEmbeddingAdapter
from app.literature_support.embedding.base import EmbeddingProfile
from app.platform.errors import AppError

MISSING = object()


def adapter_for(entries):
    return OpenAICompatibleEmbeddingAdapter(
        base_url="https://embedding.test/v1", model="test-model",
        profile=EmbeddingProfile(dimensions=3), max_retries=0,
        http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": entries}),
        )),
    )


@pytest.mark.parametrize("indices", [
    [1, 1], [MISSING, 1], [0, 2], [-1, 1], [False, 1], [0, True],
    [0.0, 1], ["0", 1], [None, 1], [0, 1, 2], [0],
], ids=["duplicate", "missing", "out-of-range", "negative", "false", "true",
        "float", "string", "null", "extra", "short"])
def test_adapter_rejects_indices_when_they_do_not_identify_each_input_once(indices):
    entries = []
    for index in indices:
        entry = {"embedding": [1, 0, 0]}
        if index is not MISSING:
            entry["index"] = index
        entries.append(entry)
    with pytest.raises(AppError) as failure:
        adapter_for(entries).embed_documents(["first", "second"])
    assert failure.value.code == "provider_unavailable"


def test_adapter_restores_input_order_when_unique_indices_arrive_out_of_order():
    entries = [{"index": 1, "embedding": [0, 1, 0]},
               {"index": 0, "embedding": [1, 0, 0]}]
    assert adapter_for(entries).embed_documents(["first", "second"]) == [
        [1, 0, 0], [0, 1, 0],
    ]


# Exact binary32 maximum and overflow rounding threshold. Values just above
# the maximum may still round to the largest finite value and are valid.
FLOAT32_MAX = float.fromhex("0x1.fffffep+127")
OVERFLOW_THRESHOLD = FLOAT32_MAX + 2.0 ** 103


@pytest.mark.parametrize("value", [
    1e300, -1e300, OVERFLOW_THRESHOLD, -OVERFLOW_THRESHOLD,
])
def test_adapter_rejects_value_when_float32_storage_would_overflow(value):
    with pytest.raises(AppError) as failure:
        adapter_for([{"index": 0, "embedding": [value, 0, 0]}]).embed_query("first")
    assert failure.value.code == "provider_unavailable"
    assert str(value) not in str(failure.value)


@pytest.mark.parametrize("value", [
    FLOAT32_MAX, -FLOAT32_MAX, FLOAT32_MAX + 2.0 ** 102,
    0.1, 1e-300, -1e-300, 0,
])
def test_adapter_keeps_value_when_float32_rounding_stays_finite(value, db_session):
    result = adapter_for([{"index": 0, "embedding": [value, 1, 0]}]).embed_query(
        "first",
    )
    # Validation is not a second normalization or quantization step.
    assert result == [value, 1, 0]
    assert struct.unpack("f", struct.pack("f", result[0]))[0] not in (
        float("inf"), -float("inf"),
    )
    db_session.execute(text(
        "CREATE TEMP TABLE vector_boundary_probe (value vector(3)) ON COMMIT DROP",
    ))
    db_session.execute(
        text("INSERT INTO vector_boundary_probe VALUES (CAST(:value AS vector))"),
        {"value": "[" + ",".join(str(component) for component in result) + "]"},
    )
    assert db_session.scalar(text("SELECT count(*) FROM vector_boundary_probe")) == 1
