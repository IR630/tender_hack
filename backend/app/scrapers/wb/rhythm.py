from __future__ import annotations

import asyncio
import random
import time

from app.core.config import settings
from app.scrapers.wb.models import RhythmState

_rate_lock = asyncio.Lock()


async def wait_before_request(state: RhythmState) -> None:
    """Async rate limit with jitter — no time.sleep."""
    async with _rate_lock:
        interval = settings.wb_min_request_interval_seconds
        jitter = random.uniform(0, interval * 0.2)
        wait = interval + jitter - (time.monotonic() - state.last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        state.last_request_at = time.monotonic()
