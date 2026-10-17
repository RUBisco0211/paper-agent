from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Uuid, false, select
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
    notify_email: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )


class ScheduleBindingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, schedule_id: str) -> ScheduleBindingRecord | None:
        return self._session.get(ScheduleBindingRecord, schedule_id)

    def get_for_update(self, schedule_id: str) -> ScheduleBindingRecord | None:
        return self._session.scalar(
            select(ScheduleBindingRecord)
            .where(ScheduleBindingRecord.schedule_id == schedule_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def cancel_notifications(self, schedule_id: str) -> None:
        from ..platform.mail import cancel_email

        cancel_email(self._session, dedupe_prefix=f"schedule-result:{schedule_id}:")

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
        self,
        schedule_id: str,
        user_id: UUID,
        project_id: UUID | None,
        notify_email: bool = False,
    ) -> ScheduleBindingRecord:
        record = ScheduleBindingRecord(
            schedule_id=schedule_id,
            user_id=user_id,
            project_id=project_id,
            notify_email=notify_email,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def delete(self, record: ScheduleBindingRecord) -> None:
        self._session.delete(record)

    def enqueue_result(
        self,
        *,
        recipient: str,
        subject: str,
        html_body: str,
        text_body: str,
        dedupe_key: str,
    ) -> None:
        from ..platform.mail import enqueue_email

        enqueue_email(
            self._session,
            recipient=recipient,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            dedupe_key=dedupe_key,
        )

    def commit(self) -> None:
        self._session.commit()
