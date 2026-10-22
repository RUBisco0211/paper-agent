from datetime import datetime
from uuid import UUID

from sqlalchemy import Index, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ServiceCredentialRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One user's credentials for one external service."""

    __tablename__ = "service_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", name="uq_service_credentials_user_kind"),
        Index("ix_service_credentials_user", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ServiceCredentialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID, kind: str) -> ServiceCredentialRecord | None:
        return self.session.execute(
            select(ServiceCredentialRecord).where(
                ServiceCredentialRecord.user_id == user_id,
                ServiceCredentialRecord.kind == kind,
            )
        ).scalar_one_or_none()

    def list_for_user(self, user_id: UUID) -> list[ServiceCredentialRecord]:
        return list(
            self.session.execute(
                select(ServiceCredentialRecord)
                .where(ServiceCredentialRecord.user_id == user_id)
                .order_by(ServiceCredentialRecord.kind)
            )
            .scalars()
            .all()
        )

    def upsert(
        self,
        user_id: UUID,
        kind: str,
        label: str,
        fields: dict,
    ) -> None:
        statement = pg_insert(ServiceCredentialRecord).values(
            user_id=user_id,
            kind=kind,
            label=label,
            fields=fields,
        )
        self.session.execute(
            statement.on_conflict_do_update(
                constraint="uq_service_credentials_user_kind",
                set_={
                    "label": statement.excluded.label,
                    "fields": statement.excluded.fields,
                    "updated_at": datetime.now().astimezone(),
                },
            )
        )
        self.session.commit()

    def delete(self, user_id: UUID, kind: str) -> None:
        record = self.get(user_id, kind)
        if record is not None:
            self.session.delete(record)
            self.session.commit()
