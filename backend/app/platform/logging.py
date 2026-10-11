import logging
import sys

import structlog
from asgi_correlation_id import correlation_id

from .config import settings


def add_request_id(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Attach the current request ID without coupling callers to ASGI state."""
    if request_id := correlation_id.get():
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging() -> None:
    """Configure application and third-party logs through one output pipeline."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    renderer = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.upper())

    for logger_name in (
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "httpx",
        "httpx2",
        "httpcore",
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    logging.captureWarnings(True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(settings.log_level.upper()),
        cache_logger_on_first_use=True,
    )
