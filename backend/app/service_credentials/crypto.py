"""Encrypt and decrypt the secret fields of one user's service credential.

The derivation mirrors AgentScope's credential storage: a master key stretched
through HKDF with the user id, so one user's ciphertext never opens for another.
"""

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_PREFIX = "enc:v1:"
_SALT = b"paper-agent:service-credential-key:v1"


class CredentialCipher:
    def __init__(self, master_key_hex: str) -> None:
        if len(master_key_hex) != 64:
            raise RuntimeError("CREDENTIAL_MASTER_KEY must be 32 random bytes in hex")
        try:
            self._master_key = bytes.fromhex(master_key_hex)
        except ValueError as exc:
            raise RuntimeError(
                "CREDENTIAL_MASTER_KEY must be 32 random bytes in hex"
            ) from exc

    def _user_key(self, user_id: str) -> bytes:
        return HKDF(
            algorithm=SHA256(),
            length=32,
            salt=_SALT,
            info=user_id.encode("utf-8"),
        ).derive(self._master_key)

    @staticmethod
    def _aad(user_id: str, kind: str, field: str) -> bytes:
        return f"paper-agent:service-credential:v1:{user_id}:{kind}:{field}".encode()

    def encrypt(self, user_id: str, kind: str, field: str, value: str) -> str:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._user_key(user_id)).encrypt(
            nonce,
            value.encode("utf-8"),
            self._aad(user_id, kind, field),
        )
        return _PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, user_id: str, kind: str, field: str, value: str) -> str:
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
                self._aad(user_id, kind, field),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise RuntimeError("credential_decryption_failed") from exc
