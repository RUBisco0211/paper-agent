"""Encrypted, transactional PostgreSQL mail outbox and SMTP transport.

A row stays locked during the bounded SMTP call. Process death rolls back the
claim so it can be recovered. A crash after SMTP acceptance can cause duplicate
mail; SMTP cannot offer exactly-once delivery.
"""

import base64
import hashlib
import json
import smtplib
import ssl
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from uuid import UUID, uuid4

import structlog
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import DateTime, Integer, String, Text, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import settings
from .database import Base, CreatedAtMixin, SessionFactory, UUIDPrimaryKeyMixin
from .errors import ProviderUnavailableError

logger = structlog.get_logger(__name__)


class MailOutboxRecord(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "mail_outbox"

    dedupe_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(48))


def _cipher() -> Fernet:
    secret = (
        settings.credential_master_key.get_secret_value() or settings.jwt_secret_key
    )
    key = hashlib.sha256(b"paper-agent-mail-outbox-v1:" + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def enqueue_email(
    session: Session,
    *,
    recipient: str,
    subject: str,
    html_body: str,
    text_body: str,
    dedupe_key: str,
    expires_at: datetime | None = None,
) -> MailOutboxRecord:
    payload = {
        "recipient": recipient,
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
    }
    # Header injection is rejected before an outbox row is created.
    if any("\r" in value or "\n" in value for value in (recipient, subject)):
        raise ValueError("Invalid mail header")
    identity = uuid4()
    session.execute(
        insert(MailOutboxRecord)
        .values(
            id=identity,
            dedupe_key=dedupe_key,
            encrypted_payload=_cipher().encrypt(json.dumps(payload).encode()).decode(),
            status="pending",
            attempts=0,
            next_attempt_at=datetime.now(UTC),
            expires_at=expires_at,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )
    return session.scalars(
        select(MailOutboxRecord).where(MailOutboxRecord.dedupe_key == dedupe_key)
    ).one()


def cancel_email(session: Session, *, dedupe_prefix: str) -> None:
    session.execute(
        update(MailOutboxRecord)
        .where(
            MailOutboxRecord.dedupe_key.startswith(dedupe_prefix, autoescape=True),
            MailOutboxRecord.status == "pending",
        )
        .values(status="cancelled", encrypted_payload="")
    )


def send_smtp(payload: dict) -> None:
    if not all(
        (
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password.get_secret_value(),
            settings.smtp_from_email,
        )
    ):
        raise ProviderUnavailableError("邮件服务尚未配置，请完成发信配置后重试")
    if settings.smtp_use_ssl == settings.smtp_starttls:
        raise ProviderUnavailableError("邮件服务需要且只能启用一种 TLS 方式")
    message = EmailMessage()
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = payload["recipient"]
    message["Subject"] = payload["subject"]
    message_domain = settings.smtp_from_email.split("@")[-1]
    message["Message-ID"] = (
        f"<{payload.get('message_id', uuid4().hex)}@{message_domain}>"
    )
    message.set_content(payload["text_body"])
    message.add_alternative(payload["html_body"], subtype="html")
    context = ssl.create_default_context()
    client_type = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    kwargs = {
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "timeout": settings.smtp_timeout_seconds,
    }
    if settings.smtp_use_ssl:
        kwargs["context"] = context
    with client_type(**kwargs) as client:
        if settings.smtp_starttls:
            client.starttls(context=context)
        client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        refused = client.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


def _failure(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, ProviderUnavailableError):
        return "smtp_not_configured", False
    if isinstance(exc, InvalidToken):
        return "payload_decryption_failed", True
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        permanent = all(int(value[0]) >= 500 for value in exc.recipients.values())
        return ("smtp_recipient_rejected" if permanent else "smtp_temporary"), permanent
    if isinstance(exc, smtplib.SMTPResponseException):
        return (
            "smtp_permanent" if exc.smtp_code >= 500 else "smtp_temporary"
        ), exc.smtp_code >= 500
    if isinstance(exc, (smtplib.SMTPException, OSError)):
        return "smtp_connection_failed", False
    return "mail_delivery_failed", False


def deliver_one(
    factory: SessionFactory,
    *,
    transport: Callable[[dict], None] = send_smtp,
    now: datetime | None = None,
    message_id: UUID | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    with factory() as session, session.begin():
        query = select(MailOutboxRecord).where(
            MailOutboxRecord.status == "pending",
            MailOutboxRecord.next_attempt_at <= now,
        )
        if message_id is not None:
            query = query.where(MailOutboxRecord.id == message_id)
        row = session.scalar(
            query.order_by(MailOutboxRecord.next_attempt_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return False
        if row.expires_at is not None and row.expires_at <= now:
            row.status = "expired"
            row.encrypted_payload = ""
            return True
        row.attempts += 1
        try:
            payload = json.loads(_cipher().decrypt(row.encrypted_payload.encode()))
            payload["message_id"] = row.id.hex
            transport(payload)
        except Exception as exc:
            error, permanent = _failure(exc)
            row.last_error = error
            row.status = (
                "failed"
                if permanent or row.attempts >= settings.mail_max_attempts
                else "pending"
            )
            row.next_attempt_at = now + timedelta(
                seconds=min(600, 15 * 2 ** (row.attempts - 1))
            )
            logger.warning(
                "mail.delivery_failed",
                mail_id=str(row.id),
                error_code=error,
                retrying=row.status == "pending",
            )
        else:
            row.status = "accepted"
            row.accepted_at = now
            row.last_error = None
            row.encrypted_payload = ""
            logger.info("mail.accepted", mail_id=str(row.id))
        return True
