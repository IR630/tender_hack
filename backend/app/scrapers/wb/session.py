from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field

import structlog
from curl_cffi.requests import AsyncSession

from app.core.config import settings
from app.scrapers.wb.circuit import circuit_is_open, reset_circuit_for_tests, trip_circuit
from app.scrapers.wb.config import (
    DEFAULT_BROWSER_HEADERS,
    MAX_RESULTS,
    SEARCH_URL,
    WB_USER_PRESETS,
    WBUserPreset,
)
from app.scrapers.wb.logging_utils import log_wb_request
from app.scrapers.wb.metrics import wb_metrics
from app.scrapers.wb.models import WBFetchLayer, WBSearchResponse
from app.scrapers.wb.proxy import (
    build_proxy_dict,
    proxy_is_configured,
    reset_exit_ip_cache,
)

struct_logger = structlog.get_logger(component="wb_session")

# Throttled WB responses sometimes return a single unrelated product in data.products.
_MIN_CATALOG_PRODUCTS = 5


def _parse_search_products(payload: dict) -> list:
    """Prefer legacy top-level products; accept data.products only for full catalogs."""
    top = payload.get("products") or []
    if top:
        return top[:MAX_RESULTS]
    data = payload.get("data")
    nested = data.get("products") or [] if isinstance(data, dict) else []
    if len(nested) >= _MIN_CATALOG_PRODUCTS:
        return nested[:MAX_RESULTS]
    return []


def _failure_priority(response: WBSearchResponse) -> tuple[int, int]:
    if response.products:
        return (0, 0)
    if response.status_code in {429, 403, 498}:
        return (3, response.status_code)
    if response.error and "пустой каталог" in response.error:
        return (1, response.status_code)
    return (2, response.status_code or 0)


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
    preset: WBUserPreset = field(default_factory=lambda: random.choice(WB_USER_PRESETS))
    proxy_session_id: str = field(default_factory=lambda: f"wb{int(time.time())}")
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
        if proxy_is_configured():
            return False
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
        self.preset = random.choice(WB_USER_PRESETS)
        reset_exit_ip_cache()

    async def _ensure_session(self) -> AsyncSession:
        if self._session is None:
            proxies = build_proxy_dict(session_id=self.proxy_session_id)
            self._session = AsyncSession(
                impersonate=self.preset.impersonate_profile,
                proxies=proxies,
            )
            self.created_at = time.monotonic()
        return self._session

    def _request_timeout(self) -> float:
        if proxy_is_configured():
            return settings.wb_proxy_timeout_seconds
        return settings.scraper_timeout_seconds

    def _should_retry_search(self, result: WBSearchResponse) -> bool:
        if result.error is None:
            return False
        if result.status_code in {429, 498, 403}:
            return True
        return proxy_is_configured() and result.status_code == 0

    async def warm_up(self) -> None:
        """GET homepage + catalog to collect cookies."""
        session = await self._ensure_session()
        started = time.perf_counter()
        try:
            home = await session.get(
                WARMUP_HOME_URL,
                headers=self._browser_headers(document=True),
                timeout=self._request_timeout(),
            )
            catalog = await session.get(
                WARMUP_CATALOG_URL,
                headers={
                    **self._browser_headers(document=True),
                    "Referer": WARMUP_HOME_URL,
                },
                timeout=self._request_timeout(),
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
                timeout=self._request_timeout(),
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
            struct_logger.warning(
                "wb_search_blocked",
                user_id=self.user_id,
                status_code=response.status_code,
                query=query,
            )
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

        products = _parse_search_products(payload)
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

    def _max_search_retries(self) -> int:
        if proxy_is_configured():
            return max(settings.wb_search_max_retries, settings.wb_proxy_max_retries)
        return settings.wb_search_max_retries

    async def _adopt_worker_session(self, worker: WBSession) -> None:
        await self.close()
        self._session = worker._session
        self.proxy_session_id = worker.proxy_session_id
        self.created_at = worker.created_at
        self.last_used = worker.last_used
        self._warmed = worker._warmed
        worker._session = None

    async def _fetch_search_proxy_race(self, params: dict[str, object]) -> WBSearchResponse:
        """Try several proxy IPs in parallel; reuse the session that succeeds."""
        started = time.perf_counter()
        best_failure: WBSearchResponse | None = None
        parallel = max(1, settings.wb_proxy_parallel_attempts)
        rounds = max(1, settings.wb_proxy_race_rounds)

        for round_idx in range(rounds):
            workers = [
                WBSession(
                    user_id=f"{self.user_id}-r{round_idx}-w{idx}",
                    proxy_session_id=f"wb{int(time.time() * 1000)}{round_idx}{idx}",
                )
                for idx in range(parallel)
            ]

            async def run_worker(worker: WBSession, idx: int) -> tuple[WBSession, WBSearchResponse]:
                query_id = f"qid{int(time.time() * 1000)}{round_idx}{idx}"
                return worker, await worker.fetch_search_once(params, query_id=query_id)

            gathered = await asyncio.gather(
                *(run_worker(worker, idx) for idx, worker in enumerate(workers)),
                return_exceptions=True,
            )

            winner: tuple[WBSession, WBSearchResponse] | None = None
            for item in gathered:
                if isinstance(item, BaseException):
                    struct_logger.warning("wb_race_worker_failed", error=str(item))
                    continue
                worker, response = item
                if response.error is None and response.products:
                    winner = (worker, response)
                    break
                if response.error and (
                    best_failure is None
                    or _failure_priority(response) > _failure_priority(best_failure)
                ):
                    best_failure = response

            for worker in workers:
                if winner is not None and worker is winner[0]:
                    continue
                await worker.close()

            if winner is not None:
                win_worker, response = winner
                await self._adopt_worker_session(win_worker)
                await win_worker.close()
                struct_logger.info(
                    "wb_proxy_race_success",
                    user_id=self.user_id,
                    round=round_idx + 1,
                    product_count=len(response.products),
                    query=params.get("query"),
                )
                log_wb_request(
                    phase="search",
                    user_id=self.user_id,
                    endpoint=SEARCH_URL,
                    status=response.status_code,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    retry_count=round_idx,
                    cache_hit=False,
                    impersonate_profile=self.preset.impersonate_profile,
                    query=params.get("query"),
                )
                await wb_metrics.record(
                    success=True,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    status_code=response.status_code,
                    fallback_level=WBFetchLayer.PRIMARY.value,
                )
                return response

            if round_idx + 1 < rounds:
                await asyncio.sleep(1.0)

        failure = best_failure or WBSearchResponse(
            [],
            status_code=429,
            error=self._http_error_message(429, ""),
        )
        struct_logger.warning(
            "wb_proxy_race_exhausted",
            user_id=self.user_id,
            rounds=rounds,
            parallel=parallel,
            query=params.get("query"),
        )
        log_wb_request(
            phase="search",
            user_id=self.user_id,
            endpoint=SEARCH_URL,
            status=failure.status_code or "failed",
            latency_ms=(time.perf_counter() - started) * 1000,
            retry_count=rounds,
            cache_hit=False,
            impersonate_profile=self.preset.impersonate_profile,
            query=params.get("query"),
        )
        await wb_metrics.record(
            success=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            status_code=failure.status_code or 0,
            fallback_level=WBFetchLayer.PRIMARY.value,
        )
        return failure

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

        if proxy_is_configured() and settings.wb_proxy_parallel_attempts > 1:
            return await self._fetch_search_proxy_race(params)

        async with self._lock:
            await self.ensure_warm()

        max_retries = self._max_search_retries()
        started = time.perf_counter()
        result: WBSearchResponse | None = None

        for attempt in range(max_retries + 1):
            query_id = f"qid{int(time.time() * 1000)}"
            result = await self.fetch_search_once(params, query_id=query_id)
            if not self._should_retry_search(result):
                break
            if attempt >= max_retries:
                break
            delay = min(
                max(
                    settings.wb_search_retry_delay_seconds * (2**attempt),
                    2.0 if proxy_is_configured() else 0.0,
                ),
                8.0,
            )
            struct_logger.warning(
                "wb_search_retry",
                user_id=self.user_id,
                attempt=attempt + 1,
                max_retries=max_retries,
                status_code=result.status_code,
                delay_seconds=delay,
            )
            await self.close()
            if proxy_is_configured():
                self.proxy_session_id = f"wb{int(time.time() * 1000)}"
            await asyncio.sleep(delay)
            async with self._lock:
                await self.ensure_warm()

        assert result is not None
        if result.status_code in {429, 498} and not proxy_is_configured():
            trip_circuit()

        log_wb_request(
            phase="search",
            user_id=self.user_id,
            endpoint=SEARCH_URL,
            status=result.status_code or "failed",
            latency_ms=(time.perf_counter() - started) * 1000,
            retry_count=max_retries if result.status_code in {429, 498, 403} else 0,
            cache_hit=False,
            impersonate_profile=self.preset.impersonate_profile,
            query=params.get("query"),
        )

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
    reset_exit_ip_cache()
    reset_circuit_for_tests()
    await wb_metrics.reset()
