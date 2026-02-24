from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog


_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog and stdlib logging for JSON output."""

    global _configured
    if _configured:
        return

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper(), 20))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), 20)),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str, **context: Any) -> structlog.stdlib.BoundLogger:
    """Return a logger bound with optional context."""

    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name).bind(**context))
