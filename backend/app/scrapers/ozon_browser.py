"""Ozon search via nodriver (background-friendly, ~25s WAF pass)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.parse import quote_plus, urljoin

import nodriver as uc
from nodriver import cdp
from selectolax.parser import HTMLParser

from app.core.config import settings

logger = logging.getLogger(__name__)

_browser_lock = asyncio.Lock()
CHALLENGE_TITLES = ("Antibot Captcha", "Antibot Challenge Page", "Доступ ограничен")


def _is_challenge(html: str) -> bool:
    if not html:
        return True
    title_m = re.search(r"<title>([^<]+)</title>", html, re.I)
    title = title_m.group(1).strip() if title_m else ""
    if title in CHALLENGE_TITLES:
        return True
    if "Похоже, нет" in html and "fab_" in html:
        return True
    if len(html) > 100_000 and "/product/" in html:
        return False
    return len(html) < 15_000 and "antibot" in html.lower()


def _parse_price_rub(text: str | None) -> int:
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", text.replace("\u202f", "").replace(" ", ""))
    if not digits:
        return 0
    return int(digits) * 100


def _extract_products(html: str) -> list[dict[str, str | int | None]]:
    tree = HTMLParser(html)
    seen: set[str] = set()
    products: list[dict[str, str | int | None]] = []

    for a in tree.css("a[href*='/product/']"):
        href = a.attributes.get("href", "")
        if not href:
            continue
        url = href if href.startswith("http") else urljoin("https://www.ozon.ru", href)
        if url in seen:
            continue
        title = a.attributes.get("title") or a.attributes.get("aria-label") or a.text(strip=True)
        if not title or len(title) < 3 or title in ("Распродажа", "Вау-цены"):
            continue
        price_text = None
        parent = a.parent
        for _ in range(5):
            if parent is None:
                break
            pm = re.search(r"([\d\s\u202f]+)\s*₽", parent.text(strip=True))
            if pm:
                price_text = pm.group(0)
                break
            parent = parent.parent
        price = _parse_price_rub(price_text)
        if price <= 0:
            continue
        img_el = a.css_first("img")
        image = None
        if img_el:
            image = img_el.attributes.get("src") or img_el.attributes.get("data-src")
        seen.add(url)
        products.append({"title": title[:300], "price": price, "url": url, "image": image})
        if len(products) >= settings.ozon_browser_max_results:
            break

    return products


async def _block_images(tab: uc.Tab) -> None:
    try:
        await tab.send(cdp.network.enable())
        await tab.send(
            cdp.network.set_blocked_urls(
                urls=["*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg", "*.ico"]
            )
        )
    except Exception:
        pass


async def fetch_search_html(query: str) -> tuple[str, str | None]:
    """Return (html, error). Uses global lock — one browser at a time."""
    url = f"https://www.ozon.ru/search/?text={quote_plus(query)}"
    headless = settings.ozon_browser_headless
    if headless is None:
        headless = not bool(os.getenv("DISPLAY"))

    async with _browser_lock:
        browser = None
        try:
            browser = await uc.start(
                headless=headless,
                browser_args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--blink-settings=imagesEnabled=false",
                ],
            )
            tab = await browser.get(url)
            await _block_images(tab)
            await tab.sleep(settings.ozon_browser_wait_seconds)
            html = await tab.get_content()
            if _is_challenge(html or ""):
                return html or "", "Ozon antibot: страница не прошла проверку WAF"
            return html or "", None
        except Exception as exc:
            logger.exception("Ozon browser fetch failed for %r", query)
            return "", str(exc)
        finally:
            if browser is not None:
                try:
                    browser.stop()
                except Exception:
                    pass


async def search_products(query: str) -> tuple[list[dict[str, str | int | None]], str | None]:
    html, error = await fetch_search_html(query)
    if error:
        return [], error
    products = _extract_products(html)
    if not products:
        return [], "Ozon: товары не найдены на странице поиска"
    return products, None
