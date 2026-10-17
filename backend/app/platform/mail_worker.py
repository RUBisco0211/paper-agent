"""Independent mail delivery process: python -m app.platform.mail_worker."""

import signal
import threading

import structlog

from .config import settings
from .database import SessionLocal
from .logging import configure_logging
from .mail import deliver_one

logger = structlog.get_logger(__name__)


def main() -> None:
    configure_logging()
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    logger.info("mail.worker_started")
    while not stopped.is_set():
        try:
            worked = deliver_one(SessionLocal)
        except Exception as exc:
            logger.error("mail.worker_failed", error_type=type(exc).__name__)
            worked = False
        if not worked:
            stopped.wait(settings.mail_poll_seconds)
    logger.info("mail.worker_stopped")


if __name__ == "__main__":
    main()
