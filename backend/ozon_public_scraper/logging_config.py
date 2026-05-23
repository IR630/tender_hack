from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

_configured = False


def _add_ts(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict["ts"] = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return event_dict


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    structlog.configure(
        processors=[
            merge_contextvars,
            _add_ts,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(component: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(component)


def bind_correlation(correlation_id: str, **extra: Any) -> None:
    bind_contextvars(correlation_id=correlation_id, **extra)


def clear_correlation() -> None:
    clear_contextvars()
