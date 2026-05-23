from __future__ import annotations

import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)

_circuit_open_until = 0.0


def circuit_is_open() -> bool:
    return time.monotonic() < _circuit_open_until


def trip_circuit() -> None:
    global _circuit_open_until
    _circuit_open_until = time.monotonic() + settings.wb_circuit_breaker_seconds
    logger.error(
        "WB circuit breaker open for %ss after block response",
        settings.wb_circuit_breaker_seconds,
    )


def reset_circuit_for_tests() -> None:
    global _circuit_open_until
    _circuit_open_until = 0.0
