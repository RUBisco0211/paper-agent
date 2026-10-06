from uuid import UUID

from sqlalchemy import ForeignKey, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import Base, CreatedAtMixin


class ScheduleBindingRecord(Base, CreatedAtMixin):
    __tablename__ = "schedule_bindings"

    schedule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class ScheduleBindingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, schedule_id: str) -> ScheduleBindingRecord | None:
        return self._session.get(ScheduleBindingRecord, schedule_id)

    def list_for_user(self, user_id: UUID) -> list[ScheduleBindingRecord]:
        return list(
            self._session.scalars(
                select(ScheduleBindingRecord)
                .where(ScheduleBindingRecord.user_id == user_id)
                .order_by(
                    ScheduleBindingRecord.created_at, ScheduleBindingRecord.schedule_id
                )
            ).all()
        )

    def has_project_tasks(self, user_id: UUID, project_id: UUID) -> bool:
        return (
            self._session.scalar(
                select(ScheduleBindingRecord.schedule_id)
                .where(
                    ScheduleBindingRecord.user_id == user_id,
                    ScheduleBindingRecord.project_id == project_id,
                )
                .limit(1)
            )
            is not None
        )

    def add(
        self, schedule_id: str, user_id: UUID, project_id: UUID
    ) -> ScheduleBindingRecord:
        record = ScheduleBindingRecord(
            schedule_id=schedule_id,
            user_id=user_id,
            project_id=project_id,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def delete(self, record: ScheduleBindingRecord) -> None:
        self._session.delete(record)

    def commit(self) -> None:
        self._session.commit()
