from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import structlog
from curl_cffi.requests import AsyncSession

from app.core.config import settings
from app.scrapers.wb.circuit import circuit_is_open, reset_circuit_for_tests, trip_circuit
from app.scrapers.wb.config import (
    DEFAULT_BROWSER_HEADERS,
    DEFAULT_WB_PRESET,
    MAX_RESULTS,
    SEARCH_URL,
    WBUserPreset,
)
from app.scrapers.wb.logging_utils import log_wb_request
from app.scrapers.wb.metrics import wb_metrics
from app.scrapers.wb.models import WBFetchLayer, WBSearchResponse

struct_logger = structlog.get_logger(component="wb_session")


WARMUP_HOME_URL = "https://www.wildberries.ru/"
WARMUP_CATALOG_URL = "https://www.wildberries.ru/catalog/elektronika/noutbuki-pereferiya/noutbuki-ultrabuki"

WARMUP_DOCUMENT_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
        "image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "max-age=0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class WBSession:
    """curl_cffi async session with cookie warmup before search API calls."""

    user_id: str = "default"
    preset: WBUserPreset = field(default_factory=lambda: DEFAULT_WB_PRESET)
    _session: AsyncSession | None = field(default=None, init=False, repr=False)
    created_at: float | None = field(default=None, init=False)
    last_used: float | None = field(default=None, init=False)
    _warmed: bool = field(default=False, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def _browser_headers(self, *, document: bool = False) -> dict[str, str]:
        headers = dict(WARMUP_DOCUMENT_HEADERS if document else DEFAULT_BROWSER_HEADERS)
        headers["User-Agent"] = self.preset.user_agent
        if not document:
            headers.update(
                {
                    "Origin": "https://www.wildberries.ru",
                    "Referer": "https://www.wildberries.ru/",
                    "x-userid": "0",
                }
            )
        return headers

    def _cookie_snapshot(self) -> dict[str, str]:
        if self._session is None:
            return {}
        try:
            return self._session.cookies.get_dict()
        except Exception as exc:
            struct_logger.warning("wb_cookie_snapshot_failed", error=str(exc))
            return {}

    def needs_warmup(self) -> bool:
        if not settings.wb_warmup_enabled:
            return False
        if self._session is None or not self._warmed or self.created_at is None:
            return True
        now = time.monotonic()
        if now - self.created_at > settings.wb_session_max_age_seconds:
            return True
        if self.last_used is not None and now - self.last_used > settings.wb_session_idle_seconds:
            return True
        return False

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
        self._session = None
        self._warmed = False
        self.created_at = None

    async def _ensure_session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(impersonate=self.preset.impersonate_profile)
            self.created_at = time.monotonic()
        return self._session

    async def warm_up(self) -> None:
        """GET homepage + catalog to collect cookies."""
        session = await self._ensure_session()
        started = time.perf_counter()
        try:
            home = await session.get(
                WARMUP_HOME_URL,
                headers=self._browser_headers(document=True),
                timeout=settings.scraper_timeout_seconds,
            )
            catalog = await session.get(
                WARMUP_CATALOG_URL,
                headers={
                    **self._browser_headers(document=True),
                    "Referer": WARMUP_HOME_URL,
                },
                timeout=settings.scraper_timeout_seconds,
            )
        except Exception as exc:
            struct_logger.warning(
                "wb_warmup_failed",
                user_id=self.user_id,
                error=str(exc),
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            self._warmed = False
            return

        latency_ms = (time.perf_counter() - started) * 1000
        cookies = self._cookie_snapshot()
        warmed_ok = (
            home.status_code == 200
            and catalog.status_code == 200
            and bool(cookies)
        )
        self._warmed = warmed_ok
        if warmed_ok:
            self.created_at = time.monotonic()
        event = "wb_warmup_complete" if warmed_ok else "wb_warmup_failed"
        log_fn = struct_logger.info if warmed_ok else struct_logger.warning
        log_fn(
            event,
            user_id=self.user_id,
            home_status=home.status_code,
            catalog_status=catalog.status_code,
            cookie_names=sorted(cookies.keys()),
            latency_ms=round(latency_ms, 2),
        )

    async def ensure_warm(self) -> None:
        if self.needs_warmup():
            await self.close()
            await self.warm_up()

    def _http_error_message(self, status_code: int, body: str) -> str:
        if status_code == 429:
            return (
                "HTTP 429: антибот Wildberries (rate-limit или IP). "
                "Подождите или используйте российский IP без VPN."
            )
        if status_code == 403:
            return "HTTP 403: доступ запрещён Wildberries."
        if status_code == 498:
            return "HTTP 498: домашний антибот Wildberries заблокировал IP."
        snippet = body.strip().replace("\n", " ")[:120]
        return f"HTTP {status_code}: {snippet or 'пустой ответ'}"

    async def _log_403_cookies(self, response) -> None:
        sent = self._cookie_snapshot()
        set_cookie = response.headers.get("set-cookie") or response.headers.get("Set-Cookie")
        struct_logger.warning(
            "wb_search_403_cookies",
            user_id=self.user_id,
            sent_cookie_names=sorted(sent.keys()),
            sent_cookies=sent,
            response_set_cookie=set_cookie,
        )

    async def fetch_search_once(
        self,
        params: dict[str, object],
        *,
        query_id: str,
    ) -> WBSearchResponse:
        session = await self._ensure_session()
        headers = {
            **self._browser_headers(),
            "x-queryid": query_id,
        }
        query = params.get("query")
        started = time.perf_counter()
        try:
            response = await session.get(
                SEARCH_URL,
                params=params,
                headers=headers,
                timeout=settings.scraper_timeout_seconds,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            log_wb_request(
                phase="search",
                user_id=self.user_id,
                endpoint=SEARCH_URL,
                status="network_error",
                latency_ms=latency_ms,
                retry_count=0,
                cache_hit=False,
                impersonate_profile=self.preset.impersonate_profile,
                error=str(exc),
            )
            return WBSearchResponse([], status_code=0, error=f"Сеть: {exc}")

        latency_ms = (time.perf_counter() - started) * 1000
        self.last_used = time.monotonic()
        pow_header = response.headers.get("x-pow") or response.headers.get("X-Pow")

        if response.status_code == 403:
            await self._log_403_cookies(response)

        log_wb_request(
            phase="search",
            user_id=self.user_id,
            endpoint=SEARCH_URL,
            status=response.status_code,
            latency_ms=latency_ms,
            retry_count=0,
            cache_hit=False,
            impersonate_profile=self.preset.impersonate_profile,
            query=query,
        )

        if response.status_code in {429, 498, 403}:
            return WBSearchResponse(
                [],
                status_code=response.status_code,
                pow_header=pow_header,
                error=self._http_error_message(response.status_code, response.text),
            )

        if response.status_code != 200:
            return WBSearchResponse(
                [],
                status_code=response.status_code,
                pow_header=pow_header,
                error=self._http_error_message(response.status_code, response.text),
            )

        try:
            payload = response.json()
        except ValueError as exc:
            struct_logger.error("wb_search_non_json", query=query, error=str(exc))
            return WBSearchResponse(
                [],
                status_code=response.status_code,
                pow_header=pow_header,
                error="Wildberries вернул не-JSON ответ",
            )

        products = (payload.get("products") or [])[:MAX_RESULTS]
        if not products:
            return WBSearchResponse(
                [],
                status_code=response.status_code,
                pow_header=pow_header,
                error="Wildberries вернул пустой каталог",
            )

        return WBSearchResponse(
            products,
            status_code=response.status_code,
            pow_header=pow_header,
        )

    async def fetch_search(self, params: dict[str, object]) -> WBSearchResponse:
        if circuit_is_open():
            return WBSearchResponse(
                [],
                status_code=0,
                error=(
                    "Wildberries временно недоступен (слишком много блокировок). "
                    f"Повторите через {int(settings.wb_circuit_breaker_seconds // 60)} мин."
                ),
            )

        async with self._lock:
            await self.ensure_warm()

        query_id = f"qid{int(time.time() * 1000)}"
        started = time.perf_counter()
        result = await self.fetch_search_once(params, query_id=query_id)

        if result.status_code in {429, 498} and settings.wb_search_max_retries > 0:
            await self.close()
            await asyncio.sleep(settings.wb_search_retry_delay_seconds)
            async with self._lock:
                await self.ensure_warm()
            query_id = f"qid{int(time.time() * 1000)}"
            result = await self.fetch_search_once(params, query_id=query_id)
            log_wb_request(
                phase="search",
                user_id=self.user_id,
                endpoint=SEARCH_URL,
                status=result.status_code or "retry_failed",
                latency_ms=(time.perf_counter() - started) * 1000,
                retry_count=1,
                cache_hit=False,
                impersonate_profile=self.preset.impersonate_profile,
                query=params.get("query"),
            )
            if result.status_code in {429, 498}:
                trip_circuit()

        latency_ms = (time.perf_counter() - started) * 1000
        success = result.error is None and bool(result.products)
        await wb_metrics.record(
            success=success,
            latency_ms=latency_ms,
            status_code=result.status_code or 0,
            fallback_level=WBFetchLayer.PRIMARY.value,
        )
        return result


wb_session = WBSession()


async def reset_session_for_tests() -> None:
    await wb_session.close()
    reset_circuit_for_tests()
    await wb_metrics.reset()
