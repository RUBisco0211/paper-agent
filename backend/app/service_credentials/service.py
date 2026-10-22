"""Store per-user credentials for services the agent calls on their behalf."""

from dataclasses import dataclass
from uuid import UUID

from ..platform.errors import ErrorCode, ProviderNotConfiguredError, ValidationError
from .domain import SPECS, spec_for
from .ports import CredentialCipher
from .repo import ServiceCredentialRecord, ServiceCredentialRepository


@dataclass(frozen=True, slots=True)
class CredentialView:
    """Public projection: secret fields are reported as set, never echoed."""

    kind: str
    label: str
    fields: dict[str, str]

    @property
    def has_api_key(self) -> bool:
        return bool(self.fields.get("api_key"))


class ServiceCredentialService:
    def __init__(
        self,
        repository: ServiceCredentialRepository,
        cipher: CredentialCipher,
    ) -> None:
        self._repository = repository
        self._cipher = cipher

    def list(self, user_id: UUID) -> list[CredentialView]:
        return [
            self._view(record) for record in self._repository.list_for_user(user_id)
        ]

    def save(
        self,
        user_id: UUID,
        kind: str,
        label: str,
        fields: dict[str, str],
    ) -> CredentialView:
        try:
            spec = spec_for(kind)
        except ValueError as exc:
            raise ValidationError(
                "不支持的服务类型", code=ErrorCode.VALIDATION_ERROR
            ) from exc
        accepted = set(spec.required_fields) | set(spec.optional_fields)
        unknown = set(fields) - accepted
        if unknown:
            raise ValidationError(
                f"不支持的字段：{', '.join(sorted(unknown))}",
                code=ErrorCode.VALIDATION_ERROR,
            )
        missing = [name for name in spec.required_fields if not fields.get(name)]
        if missing:
            raise ValidationError("缺少必填字段", code=ErrorCode.VALIDATION_ERROR)
        stored: dict[str, str] = {}
        for name, value in fields.items():
            if name in spec.secret_fields:
                stored[name] = self._cipher.encrypt(str(user_id), kind, name, value)
            else:
                stored[name] = value
        self._repository.upsert(
            user_id,
            kind,
            label or spec.label,
            stored,
        )
        record = self._repository.get(user_id, kind)
        if record is None:
            raise RuntimeError("credential_upsert_lost")
        return self._view(record)

    def delete(self, user_id: UUID, kind: str) -> None:
        self._repository.delete(user_id, kind)

    def secret(self, user_id: UUID, kind: str, field: str) -> str | None:
        """Return the decrypted value, or None when the user has not set it."""
        record = self._repository.get(user_id, kind)
        if record is None:
            return None
        value = record.fields.get(field)
        if not isinstance(value, str) or not value:
            return None
        spec = SPECS.get(kind)
        if spec is None or field not in spec.secret_fields:
            return value
        return self._cipher.decrypt(str(user_id), kind, field, value)

    def _view(self, record: ServiceCredentialRecord) -> CredentialView:
        spec = SPECS.get(record.kind)
        secret_fields = spec.secret_fields if spec else ()
        return CredentialView(
            kind=record.kind,
            label=record.label,
            fields={
                name: "<set>" if name in secret_fields else value
                for name, value in record.fields.items()
            },
        )


def require_secret(
    service: ServiceCredentialService,
    user_id: UUID,
    kind: str,
    field: str,
) -> str:
    """Read a secret or fail with a code the caller can translate for the user."""
    value = service.secret(user_id, kind, field)
    if value is None:
        raise ProviderNotConfiguredError()
    return value
