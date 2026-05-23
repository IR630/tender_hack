from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from curl_cffi import requests as curl_requests

from other_public_scraper.config import DESKTOP_UA, settings

logger = logging.getLogger(__name__)


@dataclass
class HttpResult:
    status_code: int
    body: str
    latency_ms: int
    url: str


_fetch_semaphore = asyncio.Semaphore(settings.other_fetch_concurrency)


async def fetch_html(url: str) -> HttpResult | None:
    t0 = time.perf_counter()

    def _do() -> HttpResult:
        session = curl_requests.Session(impersonate="chrome120")
        resp = session.get(
            url,
            headers={"User-Agent": DESKTOP_UA, "Accept-Language": "ru-RU,ru;q=0.9"},
            timeout=settings.other_request_timeout,
        )
        return HttpResult(
            status_code=resp.status_code,
            body=resp.text or "",
            latency_ms=int((time.perf_counter() - t0) * 1000),
            url=url,
        )

    try:
        async with _fetch_semaphore:
            result = await asyncio.to_thread(_do)
        if result.status_code >= 400:
            logger.info(
                "other_fetch_http_error url=%s status=%d latency_ms=%d",
                url,
                result.status_code,
                result.latency_ms,
            )
            return None
        if len(result.body) < 200:
            logger.info(
                "other_fetch_empty_body url=%s status=%d body_len=%d latency_ms=%d",
                url,
                result.status_code,
                len(result.body),
                result.latency_ms,
            )
            return None
        logger.info(
            "other_fetch_ok url=%s status=%d body_len=%d latency_ms=%d",
            url,
            result.status_code,
            len(result.body),
            result.latency_ms,
        )
        return result
    except Exception as exc:
        logger.info("other_fetch_exception url=%s error=%s", url, exc)
        return None
