"""Encrypted AgentScope SQL credentials with owner-safe public projections."""

import base64
import binascii
import os
from collections.abc import Callable
from typing import Self

from agentscope.app.storage import AsyncSQLAlchemyStorage, CredentialRecord
from agentscope.app.storage._sql._tables import CredentialRow
from agentscope.credential import CredentialBase
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select

from app.platform.config import settings

_PREFIX = "enc:v1:"
_SALT = b"paper-agent:credential-key:v1"


class PublicCredentialRecord(CredentialRecord):
    """Runtime data stays readable; framework views never serialize its key."""

    def model_dump(self, *args, **kwargs) -> dict:
        payload = super().model_dump(*args, **kwargs)
        if isinstance(payload.get("data"), dict):
            payload["data"] = {
                name: value
                for name, value in payload["data"].items()
                if name != "api_key"
            }
        return payload


class EncryptedCredentialStorage(AsyncSQLAlchemyStorage):
    """Preserve AgentScope storage behavior except credential encryption."""

    def __init__(
        self,
        url: str,
        *,
        key_provider: Callable[[], str],
        **kwargs,
    ) -> None:
        super().__init__(url, **kwargs)
        self._key_provider = key_provider
        self._master_key: bytes | None = None

    async def __aenter__(self) -> Self:
        encoded = self._key_provider()
        if len(encoded) != 64:
            raise RuntimeError("CREDENTIAL_MASTER_KEY must be 32 random bytes in hex")
        try:
            self._master_key = bytes.fromhex(encoded)
        except ValueError as exc:
            raise RuntimeError(
                "CREDENTIAL_MASTER_KEY must be 32 random bytes in hex"
            ) from exc
        await super().__aenter__()
        try:
            await self._migrate_and_verify_credentials()
        except Exception:
            await self.aclose()
            raise
        return self

    def _user_key(self, user_id: str) -> bytes:
        if self._master_key is None:
            raise RuntimeError("Credential storage is not initialized")
        return HKDF(
            algorithm=SHA256(),
            length=32,
            salt=_SALT,
            info=user_id.encode("utf-8"),
        ).derive(self._master_key)

    @staticmethod
    def _aad(user_id: str, credential_id: str) -> bytes:
        return f"paper-agent-credential:v1:{user_id}:{credential_id}".encode()

    def _encrypt(self, user_id: str, credential_id: str, value: str) -> str:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._user_key(user_id)).encrypt(
            nonce,
            value.encode("utf-8"),
            self._aad(user_id, credential_id),
        )
        return _PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def _decrypt(self, user_id: str, credential_id: str, value: str) -> str:
        if not value.startswith(_PREFIX):
            raise RuntimeError("credential_decryption_failed")
        try:
            payload = base64.urlsafe_b64decode(value[len(_PREFIX) :])
            if len(payload) < 29:
                raise ValueError("short ciphertext")
            nonce, ciphertext = payload[:12], payload[12:]
            plaintext = AESGCM(self._user_key(user_id)).decrypt(
                nonce,
                ciphertext,
                self._aad(user_id, credential_id),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise RuntimeError("credential_decryption_failed") from exc

    async def _migrate_and_verify_credentials(self) -> None:
        """Encrypt pre-adapter records and fail boot with a wrong master key."""
        async with self._session() as session:
            rows = (await session.execute(select(CredentialRow))).scalars().all()
            for row in rows:
                data = row.payload.get("data", {})
                secret = data.get("api_key")
                if not isinstance(secret, str):
                    continue
                if secret.startswith(_PREFIX):
                    self._decrypt(row.user_id, row.id, secret)
                else:
                    row.payload = {
                        **row.payload,
                        "data": {
                            **data,
                            "api_key": self._encrypt(row.user_id, row.id, secret),
                        },
                    }
            await session.commit()

    @staticmethod
    def _validate_credential(credential: CredentialBase) -> CredentialBase:
        provider = getattr(credential, "type", "").removesuffix("_credential")
        if provider not in settings.llm_providers:
            raise HTTPException(status_code=422, detail="Provider not allowed")
        field = type(credential).model_fields.get("base_url")
        if field is not None:
            expected = settings.credential_base_urls.get(provider, field.default)
            if credential.base_url not in {field.default, expected}:
                raise HTTPException(status_code=422, detail="Base URL not allowed")
            credential = credential.model_copy(update={"base_url": expected})
        api_key = getattr(credential, "api_key", None)
        if not isinstance(api_key, SecretStr) or not api_key.get_secret_value():
            raise HTTPException(status_code=422, detail="API key required")
        return credential

    async def upsert_credential(
        self,
        user_id: str,
        credential_data: CredentialBase,
    ) -> str:
        credential_data = self._validate_credential(credential_data)
        encrypted = self._encrypt(
            user_id,
            credential_data.id,
            credential_data.api_key.get_secret_value(),
        )
        stored = credential_data.model_copy(
            update={"api_key": SecretStr(encrypted)},
        )
        return await super().upsert_credential(user_id, stored)

    async def get_credential(
        self,
        user_id: str,
        credential_id: str,
    ) -> CredentialRecord | None:
        record = await super().get_credential(user_id, credential_id)
        if record is None:
            return None
        data = dict(record.data)
        if "api_key" in data:
            data["api_key"] = self._decrypt(user_id, record.id, data["api_key"])
        return PublicCredentialRecord.model_validate(
            {**record.model_dump(), "data": data},
        )

    async def list_credentials(self, user_id: str) -> list[CredentialRecord]:
        records = await super().list_credentials(user_id)
        return [
            PublicCredentialRecord.model_validate(record.model_dump())
            for record in records
        ]
