"""Ozon search via nodriver with fail-fast WAF handling."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from urllib.parse import quote_plus

import nodriver as uc
import structlog

from app.core.browser_semaphore import ozon_browser_semaphore
from app.core.config import settings
from app.scrapers.ozon_seo_common import extract_products
from cache_manager import get_cached_products, set_cached_products

logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger(component="ozon_browser")

T = TypeVar("T")

CHALLENGE_TITLES = ("Antibot Captcha", "Antibot Challenge Page", "Доступ ограничен")
WAF_BLOCK_MARKERS = ("abt-challenge/incidents", "Похоже, нет", "fab_")
WAF_BLOCK_MAX_HTML_LEN = 15_000
OZON_HOME_URL = "https://www.ozon.ru/"
OZON_WAF_STATUS = "blocked_by_waf"
OZON_WAF_MESSAGE = "Ozon: доступ временно ограничен защитой маркетплейса"
POLL_INTERVAL_SECONDS = 2.0
DETAIL_EXTRA_WAIT_SECONDS = 3.0


def _is_challenge(html: str) -> bool:
    if not html:
        return True
    title_m = re.search(r"<title>([^<]+)</title>", html, re.I)
    title = title_m.group(1).strip() if title_m else ""
    if title in CHALLENGE_TITLES:
        return True
    if WAF_BLOCK_MARKERS[0] in html and len(html) < WAF_BLOCK_MAX_HTML_LEN:
        return True
    if WAF_BLOCK_MARKERS[1] in html and WAF_BLOCK_MARKERS[2] in html:
        return True
    return len(html) < WAF_BLOCK_MAX_HTML_LEN and "antibot" in html.lower()


def _is_warmup_ready(html: str) -> bool:
    if _is_challenge(html):
        return False
    return len(html) >= WAF_BLOCK_MAX_HTML_LEN or html.count("data-widget") >= 5


def _is_product_detail_ready(html: str) -> bool:
    """Product SPA renders description/characteristics asynchronously after first paint."""
    if _is_challenge(html):
        return False
    if re.search(r'property="og:description"\s+content="[^"]{10,}"', html, re.I):
        return True
    if html.count("data-widget") >= 20:
        return True
    return False


def _is_search_ready(html: str) -> bool:
    if _is_challenge(html):
        return False
    return "/product/" in html and "₽" in html


def _waf_block_result() -> tuple[list[dict[str, Any]], str, str]:
    return [], OZON_WAF_MESSAGE, OZON_WAF_STATUS


def _browser_headless() -> bool:
    return settings.ozon_browser_headless


def _browser_args() -> list[str]:
    # Keep custom flags minimal — Chrome shows a warning bar for unsupported flags like
    # --disable-blink-features=AutomationControlled and Ozon antibot treats them as automation.
    return [
        "--window-size=1920,1080",
    ]


def _browser_executable_path() -> str | None:
    return os.getenv("CHROME_BIN") or os.getenv("GOOGLE_CHROME_BIN")


async def _start_browser() -> uc.Browser:
    start_kwargs: dict[str, Any] = {
        "headless": _browser_headless(),
        "lang": "ru-RU",
        "browser_args": _browser_args(),
        "sandbox": True,
    }
    chrome_bin = _browser_executable_path()
    if chrome_bin:
        start_kwargs["browser_executable_path"] = chrome_bin
    return await uc.start(**start_kwargs)


async def _set_ozon_city(browser: uc.Browser, *, city_name: str) -> bool:
    """Simulate city selection via Ozon's UI so regional prices are applied."""
    try:
        tab = await browser.get(OZON_HOME_URL)
        await tab.sleep(2.0)

        location_btn = None
        for selector in (
            'div[data-widget="locationSelector"]',
            'button[aria-label*="город"]',
        ):
            try:
                location_btn = await tab.select(selector)
                if location_btn:
                    break
            except Exception:
                pass

        if not location_btn:
            struct_logger.warning("ozon_set_city_no_btn", city_name=city_name)
            return False

        await location_btn.click()
        await tab.sleep(1.5)

        city_input = None
        try:
            city_input = await tab.select('input[placeholder*="город"]')
        except Exception:
            pass

        if not city_input:
            struct_logger.warning("ozon_set_city_no_input", city_name=city_name)
            return False

        await city_input.send_keys(city_name)
        await tab.sleep(1.5)

        suggestion = None
        for sel in ('[data-index="0"]', 'ul[role="listbox"] li', '[class*="suggestion"] li'):
            try:
                suggestion = await tab.select(sel)
                if suggestion:
                    break
            except Exception:
                pass

        if not suggestion:
            struct_logger.warning("ozon_set_city_no_suggestion", city_name=city_name)
            return False

        await suggestion.click()
        await tab.sleep(2.5)
        struct_logger.info("ozon_set_city_ok", city_name=city_name)
        return True
    except Exception as exc:
        struct_logger.warning("ozon_set_city_error", city_name=city_name, error=str(exc))
        return False


async def _warmup_interact(tab: uc.Tab) -> None:
    """Light scroll/mouse activity — Ozon __rr=1 redirect often needs a real session."""
    try:
        await tab.scroll_down(400)
        await tab.sleep(1.0)
        await tab.scroll_down(600)
        await tab.sleep(0.5)
    except Exception:
        pass


async def _warmup_browser(browser: uc.Browser, *, label: str) -> str | None:
    """Visit ozon.ru homepage to pass WAF and collect cookies before search."""
    if not settings.ozon_browser_warmup_home:
        return None
    home_tab = await browser.get(OZON_HOME_URL)
    await home_tab.sleep(settings.ozon_browser_warmup_seconds)
    await _warmup_interact(home_tab)
    home_html, home_ok = await _poll_until_ready(
        home_tab,
        settings.ozon_browser_warmup_seconds + settings.ozon_browser_wait_seconds,
        warmup=True,
    )
    if not home_ok and _is_challenge(home_html):
        struct_logger.info("ozon_browser_warmup_retry_page", query=label, html_len=len(home_html))
        await home_tab.sleep(4.0)
        try:
            await home_tab.reload()
        except Exception:
            pass
        await home_tab.sleep(2.0)
        await _warmup_interact(home_tab)
        home_html, home_ok = await _poll_until_ready(
            home_tab,
            settings.ozon_browser_warmup_seconds + settings.ozon_browser_wait_seconds,
            warmup=True,
        )
    if home_ok or _is_warmup_ready(home_html):
        struct_logger.info("ozon_browser_warmup_ok", query=label, html_len=len(home_html))
        return None
    struct_logger.warning("ozon_browser_warmup_challenge", query=label, html_len=len(home_html))
    return "waf"


async def _poll_until_ready(
    tab: uc.Tab,
    max_seconds: float,
    *,
    require_products: bool = False,
    require_product_detail: bool = False,
    warmup: bool = False,
) -> tuple[str, bool]:
    deadline = time.monotonic() + max_seconds
    html = ""
    while time.monotonic() < deadline:
        html = await tab.get_content()
        if require_product_detail:
            ready = _is_product_detail_ready(html or "")
        elif require_products:
            ready = _is_search_ready(html or "")
        elif warmup:
            ready = _is_warmup_ready(html or "")
        else:
            ready = not _is_challenge(html or "")
        if ready:
            return html or "", True
        await tab.sleep(POLL_INTERVAL_SECONDS)
    return html or "", False


async def navigate_and_get_html(
    browser: uc.Browser,
    url: str,
    *,
    wait_seconds: float,
    require_products: bool = False,
    require_product_detail: bool = False,
) -> tuple[str, str | None]:
    tab = await browser.get(url)
    if require_product_detail:
        await tab.sleep(1.5)
    html, ok = await _poll_until_ready(
        tab,
        wait_seconds,
        require_products=require_products,
        require_product_detail=require_product_detail,
    )
    if require_product_detail and ok:
        try:
            await tab.scroll_down(800)
            await tab.sleep(1.5)
            await tab.scroll_down(1200)
            await tab.sleep(DETAIL_EXTRA_WAIT_SECONDS)
            html = await tab.get_content()
            if not _is_product_detail_ready(html or ""):
                html, ok = await _poll_until_ready(
                    tab,
                    DETAIL_EXTRA_WAIT_SECONDS + 4.0,
                    require_product_detail=True,
                )
        except Exception:
            pass
    if require_products and ok:
        try:
            from app.scrapers.ozon_seo_common import _extract_broad_from_html_cards

            html = await tab.get_content()
            for _ in range(15):
                cards = _extract_broad_from_html_cards(html, max_results=48)
                if len(cards) >= settings.ozon_ml_top_k:
                    break
                await tab.scroll_down(1200)
                await tab.sleep(1.0)
                html = await tab.get_content()
        except Exception:
            pass
    if ok:
        return html, None
    if _is_challenge(html or ""):
        return html or "", "waf"
    return html or "", "empty"


def is_challenge(html: str) -> bool:
    return _is_challenge(html)


def waf_block_result() -> tuple[list[dict[str, Any]], str, str]:
    return _waf_block_result()


async def run_browser_pipeline[T](
    label: str,
    handler: Callable[[uc.Browser], Awaitable[tuple[T, str | None]]],
    *,
    timeout_seconds: float | None = None,
    city_name: str | None = None,
) -> tuple[T | None, str | None]:
    """Single browser session under global semaphore — reuse cookies across navigations."""
    timeout = timeout_seconds or settings.ozon_pipeline_timeout_seconds
    max_attempts = max(1, settings.ozon_browser_max_retries + 1)

    if ozon_browser_semaphore.locked():
        struct_logger.info("ozon_browser_queued", query=label, message="Запрос поставлен в очередь")

    async with ozon_browser_semaphore:
        for attempt in range(1, max_attempts + 1):
            browser: uc.Browser | None = None
            headless = _browser_headless()
            struct_logger.info(
                "ozon_browser_pipeline_start",
                query=label,
                attempt=attempt,
                max_attempts=max_attempts,
                timeout_seconds=timeout,
                display=os.getenv("DISPLAY"),
                headless=headless,
            )
            if headless:
                struct_logger.warning(
                    "ozon_browser_headless_enabled",
                    query=label,
                    message="Headless mode triggers Ozon WAF — set OZON_BROWSER_HEADLESS=false",
                )
            try:
                browser = await _start_browser()
                warmup_error = await _warmup_browser(browser, label=label)
                if warmup_error != "waf" and city_name:
                    city_ok = await _set_ozon_city(browser, city_name=city_name)
                    if not city_ok:
                        struct_logger.warning("ozon_set_city_failed", query=label, city=city_name)
                if warmup_error == "waf" and attempt < max_attempts:
                    struct_logger.warning("ozon_browser_warmup_retry", query=label, attempt=attempt)
                    await asyncio.sleep(settings.ozon_browser_retry_delay_seconds)
                    continue

                result, error = await asyncio.wait_for(handler(browser), timeout=timeout)
                if error is None:
                    return result, None
                if error in ("empty", "waf") and attempt < max_attempts:
                    struct_logger.warning(
                        "ozon_browser_pipeline_retry",
                        query=label,
                        attempt=attempt,
                        error=error,
                    )
                    await asyncio.sleep(settings.ozon_browser_retry_delay_seconds)
                    continue
                return result, error
            except TimeoutError:
                struct_logger.warning(
                    "ozon_browser_pipeline_timeout",
                    query=label,
                    attempt=attempt,
                    timeout_seconds=timeout,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(settings.ozon_browser_retry_delay_seconds)
                    continue
                return None, "timeout"
            except Exception as exc:
                logger.exception("Ozon browser pipeline failed for %r", label)
                return None, str(exc)
            finally:
                if browser is not None:
                    try:
                        browser.stop()
                    except Exception:
                        pass

    return None, "waf"


async def _run_browser_session(
    url: str,
    *,
    label: str,
    wait_seconds: float,
    require_products: bool = False,
    require_product_detail: bool = False,
    city_name: str | None = None,
) -> tuple[str, str | None]:
    async def _handler(browser: uc.Browser) -> tuple[str, str | None]:
        return await navigate_and_get_html(
            browser,
            url,
            wait_seconds=wait_seconds,
            require_products=require_products,
            require_product_detail=require_product_detail,
        )

    extra_timeout = 30.0 if require_product_detail else 20.0
    html, error = await run_browser_pipeline(
        label,
        _handler,
        timeout_seconds=wait_seconds + extra_timeout,
        city_name=city_name,
    )
    if html is None:
        return "", error or "waf"
    return html, error


async def _fetch_url_uncached(
    url: str,
    *,
    label: str,
    timeout_seconds: float,
    wait_seconds: float,
    require_products: bool = False,
    require_product_detail: bool = False,
    city_name: str | None = None,
) -> tuple[str, str | None]:
    html, error = await _run_browser_session(
        url,
        label=label,
        wait_seconds=wait_seconds,
        require_products=require_products,
        require_product_detail=require_product_detail,
        city_name=city_name,
    )
    if error == "timeout":
        struct_logger.warning(
            "ozon_fail_fast_timeout",
            query=label,
            timeout_seconds=timeout_seconds,
        )
    if error == "waf":
        struct_logger.warning("ozon_fail_fast_waf", query=label, phase="fetch")
    return html, error


async def _fetch_search_html_uncached(
    query: str, region: str | None = None
) -> tuple[str, str | None]:
    from app.core.regions import resolve_region

    city_name = resolve_region(region).ozon_city_name
    search_url = f"https://www.ozon.ru/search/?text={quote_plus(query)}"
    return await _fetch_url_uncached(
        search_url,
        label=query,
        timeout_seconds=settings.ozon_browser_total_timeout_seconds,
        wait_seconds=settings.ozon_browser_wait_seconds,
        require_products=True,
        city_name=city_name,
    )


async def fetch_product_html(url: str) -> tuple[str, str | None]:
    return await _fetch_url_uncached(
        url,
        label=url,
        timeout_seconds=settings.ozon_enrich_timeout_seconds,
        wait_seconds=settings.ozon_enrich_wait_seconds,
        require_product_detail=True,
    )


async def search_products(
    query: str,
    *,
    region: str | None = None,
    skip_cache: bool = False,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Return (products, error_message, source_status)."""
    if settings.ozon_two_stage_enabled:
        from app.scrapers.two_stage_ozon import parser as two_stage_parser

        return await two_stage_parser.search(query, skip_cache=skip_cache)

    cache_key = f"{region or 'default'}:{query}"
    if settings.ozon_browser_cache_enabled and not skip_cache:
        cached = get_cached_products(cache_key)
        if cached is not None:
            return cached, None, None

    html, error = await _fetch_search_html_uncached(query, region)
    if error in ("timeout", "waf"):
        return _waf_block_result()
    if error:
        struct_logger.warning("ozon_fail_fast_error", query=query, error=error)
        if "antibot" in error.lower() or "waf" in error.lower():
            return _waf_block_result()
        return [], error, None

    products = extract_products(html, max_results=settings.ozon_browser_max_results)
    if not products:
        if _is_challenge(html):
            return _waf_block_result()
        return [], "Ozon: товары не найдены на странице поиска", None

    if settings.ozon_browser_cache_enabled:
        set_cached_products(cache_key, products, ttl=settings.ozon_browser_cache_ttl_seconds)

    return products, None, None
