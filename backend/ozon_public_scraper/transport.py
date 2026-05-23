from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from curl_cffi import requests as curl_requests

from ozon_public_scraper.config import DESKTOP_UA, settings
from ozon_public_scraper.logging_config import get_logger

logger = get_logger("ozon_public.transport")

_ozon_semaphore = asyncio.Semaphore(settings.ozon_max_concurrent)
_last_ozon_request_at = 0.0
_rate_lock = asyncio.Lock()


@dataclass
class HttpResult:
    status_code: int
    body: bytes
    latency_ms: int
    url: str


def _desktop_headers(
    *,
    accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
) -> dict[str, str]:
    return {
        "User-Agent": DESKTOP_UA,
        "Accept": accept,
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }


async def _apply_rate_limit(domain: str, reason: str) -> None:
    global _last_ozon_request_at
    async with _rate_lock:
        interval = settings.ozon_request_interval_ms / 1000.0
        waited = interval - (time.monotonic() - _last_ozon_request_at)
        if waited > 0:
            logger.info(
                "rate_limit_applied",
                context={"domain": domain, "waited_ms": int(waited * 1000), "reason": reason},
            )
            await asyncio.sleep(waited)
        _last_ozon_request_at = time.monotonic()


async def fetch_url(
    url: str,
    *,
    user_agent: str | None = None,
    accept: str | None = None,
    apply_ozon_limit: bool = False,
) -> HttpResult:
    headers = _desktop_headers()
    if accept:
        headers["Accept"] = accept
    if user_agent:
        headers["User-Agent"] = user_agent

    if apply_ozon_limit:
        await _apply_rate_limit("ozon.ru", "inter_request_interval")

    t0 = time.perf_counter()

    def _do_request() -> HttpResult:
        session = curl_requests.Session(impersonate="chrome131")
        resp = session.get(url, headers=headers, timeout=settings.ozon_request_timeout)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return HttpResult(
            status_code=resp.status_code,
            body=resp.content or b"",
            latency_ms=latency_ms,
            url=url,
        )

    if apply_ozon_limit:
        async with _ozon_semaphore:
            return await asyncio.to_thread(_do_request)
    return await asyncio.to_thread(_do_request)
