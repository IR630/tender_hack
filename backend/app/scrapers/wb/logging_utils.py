from __future__ import annotations

import time
from typing import Any

import structlog

logger = structlog.get_logger(component="wb")


def log_wb_request(
    *,
    phase: str,
    user_id: str,
    endpoint: str,
    status: int | str,
    latency_ms: float,
    retry_count: int,
    cache_hit: bool,
    impersonate_profile: str,
    **extra: Any,
) -> None:
    logger.info(
        "wb_request",
        timestamp=time.time(),
        phase=phase,
        user_id=user_id,
        endpoint=endpoint,
        status=status,
        latency_ms=round(latency_ms, 2),
        retry_count=retry_count,
        cache_hit=cache_hit,
        impersonate_profile=impersonate_profile,
        **extra,
    )
