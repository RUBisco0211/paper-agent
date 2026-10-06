"""Valid, nonproduction master key for AgentScope integration tests."""

import pytest
from pydantic import SecretStr

from app.platform.config import settings


@pytest.fixture(autouse=True)
def credential_master_key_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))
