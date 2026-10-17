import smtplib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.platform.config import settings
from app.platform.mail import MailOutboxRecord, cancel_email, deliver_one, enqueue_email
from app.platform.mail_templates import schedule_result_email, verification_email


def queue(session, **overrides):
    values: dict[str, Any] = {
        "recipient": "reader@example.com",
        "subject": "Verification",
        "html_body": "<p>123456</p>",
        "text_body": "123456",
        "dedupe_key": "auth-code:test",
    }
    values.update(overrides)
    return enqueue_email(session, **values)


def test_outbox_encrypts_content_and_deduplicates_when_message_is_queued_twice(
    db_session,
):
    first = queue(db_session)
    second = queue(db_session)
    db_session.commit()
    assert first.id == second.id
    assert "123456" not in first.encrypted_payload
    assert "reader@example.com" not in first.encrypted_payload
    assert len(list(db_session.scalars(select(MailOutboxRecord)))) == 1


def test_outbox_marks_accepted_when_transport_accepts_message(
    db_session, session_factory
):
    record = queue(db_session)
    db_session.commit()
    sent = []
    assert deliver_one(session_factory, transport=lambda payload: sent.append(payload))
    db_session.expire_all()
    assert db_session.get(MailOutboxRecord, record.id).status == "accepted"
    assert sent[0]["text_body"] == "123456"


def test_outbox_retries_without_losing_message_when_smtp_is_temporarily_unavailable(
    db_session, session_factory
):
    record = queue(db_session)
    db_session.commit()

    def reject(payload):
        raise smtplib.SMTPResponseException(451, b"private provider response")

    deliver_one(session_factory, transport=reject)
    db_session.expire_all()
    stored = db_session.get(MailOutboxRecord, record.id)
    assert stored.status == "pending"
    assert stored.attempts == 1
    assert stored.last_error == "smtp_temporary"
    assert stored.next_attempt_at > datetime.now(UTC)


def test_outbox_stops_retrying_when_smtp_permanently_rejects_recipient(
    db_session, session_factory
):
    record = queue(db_session)
    db_session.commit()

    def reject(payload):
        raise smtplib.SMTPRecipientsRefused({"reader@example.com": (550, b"private")})

    deliver_one(session_factory, transport=reject)
    db_session.expire_all()
    assert db_session.get(MailOutboxRecord, record.id).status == "failed"


def test_outbox_does_not_send_when_verification_has_expired(
    db_session, session_factory
):
    record = queue(db_session, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    db_session.commit()
    sent = []
    deliver_one(session_factory, transport=lambda payload: sent.append(payload))
    db_session.expire_all()
    assert sent == []
    assert db_session.get(MailOutboxRecord, record.id).status == "expired"


def test_outbox_cancels_only_matching_pending_mail_when_task_is_disabled(
    db_session, session_factory
):
    record = queue(db_session, dedupe_key="schedule-result:task:run")
    other = queue(db_session, dedupe_key="schedule-result:other:run")
    db_session.commit()
    cancel_email(db_session, dedupe_prefix="schedule-result:task:")
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(MailOutboxRecord, record.id).status == "cancelled"
    assert db_session.get(MailOutboxRecord, other.id).status == "pending"


def test_result_template_renders_safe_markdown_when_content_contains_active_html():
    _, html, text = schedule_result_email(
        name="Review",
        markdown="# Findings\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```py\nprint(1)\n```\n\n<script>bad()</script>\n\n[bad](javascript:alert(1))\n\n![private](https://remote.invalid/secret.png)\n\n$x^2$",
        status="success",
        run_url="https://papers.example/scheduled/task/runs/run",
    )
    assert "<table" in html and "<pre" in html
    assert "<script>" not in html
    assert 'href="javascript:' not in html
    assert "<img" not in html
    assert "https://remote.invalid" not in html + text
    assert "$x^2$" in html
    assert "https://papers.example/scheduled/task/runs/run" in html + text


def test_result_template_reports_truncation_when_html_exceeds_limit(monkeypatch):
    monkeypatch.setattr(settings, "mail_body_max_bytes", 8000)
    _, html, text = schedule_result_email(
        name="Review",
        markdown="长结果 " * 10000,
        status="success",
        run_url="https://papers.example/run",
    )
    assert len(html.encode()) <= 8000
    assert "仅展示部分" in html and "仅展示部分" in text
    assert "https://papers.example/run" in html and "https://papers.example/run" in text


def test_failure_template_excludes_partial_answer_when_run_fails():
    _, html, text = schedule_result_email(
        name="Review",
        markdown="private partial",
        status="failed",
        error="请检查模型配置后重新运行。",
        run_url="https://papers.example/run",
    )
    assert "private partial" not in html + text
    assert "请检查模型" in html and "请检查模型" in text


def test_result_template_preserves_latex_when_delimiters_and_alignment_are_present():
    from html import escape

    formulas = [
        r"\(x^2\)",
        r"\[\frac{a}{b}\]",
        r"$$\begin{aligned} a &= b \\ c &= d \end{aligned}$$",
        "$$\n\\begin{aligned}\n\na &= b \\\\\nc &= d\n\\end{aligned}\n$$",
    ]
    _, html, text = schedule_result_email(
        name="Review",
        markdown="\n\n".join(formulas),
        status="success",
        run_url="https://papers.example/run",
    )
    for formula in formulas:
        assert escape(formula) in html
        assert formula in text


def test_verification_template_separates_purpose_when_reset_is_requested():
    subject, html, text = verification_email("123456", "password_reset")
    assert "重置" in subject
    assert "123456" in html and "123456" in text
    assert "10 分钟" in text
