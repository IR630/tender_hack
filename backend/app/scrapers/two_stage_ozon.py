"""Two-stage Ozon pipeline: broad search → ML filter → optional deep enrichment."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote_plus, urlencode

import structlog

from app.core.config import settings
from app.scrapers import ozon_browser
from app.scrapers.ozon_ml_filter import filter_top_k_by_similarity
from app.scrapers.ozon_seo_common import (
    build_search_preview_description,
    extract_broad_search_products,
    extract_product_enrichment,
)

logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger(component="two_stage_ozon")


def _build_search_url(query: str, category_id: str | None = None) -> str:
    params: dict[str, str] = {"text": query.strip()}
    if category_id:
        params["category"] = category_id
    return f"https://www.ozon.ru/search/?{urlencode(params, quote_via=quote_plus)}"


def _build_description(prose: str | None, characteristics: dict[str, str]) -> str:
    lines: list[str] = []
    if prose and prose.strip():
        lines.append(prose.strip())
        lines.append("")
    if characteristics:
        lines.append("Характеристики:")
        for label, value in characteristics.items():
            lines.append(f"• {label}: {value}")
    return "\n".join(lines).strip()


def _apply_enrichment(product: dict[str, Any], detail: dict[str, Any]) -> None:
    prose = str(detail.get("description") or "").strip()
    characteristics = dict(detail.get("characteristics") or {})
    if characteristics:
        product["characteristics"] = characteristics
    combined = _build_description(prose, characteristics)
    if combined:
        product["description"] = combined


def _preview_to_product(preview: dict[str, Any]) -> dict[str, Any]:
    description = preview.get("description") or build_search_preview_description(preview)
    return {
        "title": preview.get("title"),
        "price": preview.get("price"),
        "url": preview.get("url"),
        "image": preview.get("image"),
        "description": description,
        "characteristics": dict(preview.get("characteristics") or {}),
        "similarity": preview.get("similarity"),
        "rating": preview.get("rating"),
        "reviews_count": preview.get("reviews_count"),
    }


def _map_pipeline_error(error: str | None) -> tuple[list[dict[str, Any]], str | None, str | None]:
    if error in ("waf", "timeout"):
        return ozon_browser.waf_block_result()
    if error:
        if "antibot" in error.lower() or "waf" in error.lower():
            return ozon_browser.waf_block_result()
        return [], error, None
    return [], "Ozon: товары не найдены на странице поиска", None


class TwoStageOzonParser:
    """Broad search (30+) → rubert top-5 → optional enrich in the same browser session."""

    async def search(
        self,
        query: str,
        *,
        category_id: str | None = None,
        region: str | None = None,
        skip_cache: bool = False,
        on_partial_raw=None,
    ) -> tuple[list[dict[str, Any]], str | None, str | None]:
        cache_key = f"{region or 'default'}:{query}"
        if settings.ozon_browser_cache_enabled and not skip_cache:
            from cache_manager import get_cached_products

            cached = get_cached_products(cache_key)
            if cached is not None:
                return cached, None, None

        search_url = _build_search_url(query, category_id)
        partial_emitted = False

        async def emit_partial_from_html(search_html: str) -> None:
            nonlocal partial_emitted
            if partial_emitted or not on_partial_raw:
                return
            previews = extract_broad_search_products(search_html, max_results=5)
            if not previews:
                return
            partial_emitted = True
            await on_partial_raw([_preview_to_product(preview) for preview in previews])

        async def pipeline(browser) -> tuple[list[dict[str, Any]], str | None]:
            search_html, search_error = await ozon_browser.navigate_and_get_html(
                browser,
                search_url,
                wait_seconds=settings.ozon_browser_wait_seconds,
                require_products=True,
                on_products_html=emit_partial_from_html if on_partial_raw else None,
            )
            if search_error:
                return [], search_error

            previews = extract_broad_search_products(
                search_html,
                max_results=settings.ozon_broad_search_max,
            )
            struct_logger.info("ozon_broad_search_done", query=query, count=len(previews))
            if not previews:
                if ozon_browser.is_challenge(search_html):
                    return [], "waf"
                return [], "empty"

            top_k = filter_top_k_by_similarity(
                query,
                previews,
                top_k=settings.ozon_ml_top_k,
            )
            products = [_preview_to_product(p) for p in top_k]

            if not settings.ozon_enrich_enabled:
                struct_logger.info(
                    "ozon_enrich_skipped",
                    query=query,
                    count=len(products),
                    reason="disabled",
                )
                return products, None

            enrich_limit = max(0, settings.ozon_enrich_max_products)
            for index, product in enumerate(products[:enrich_limit]):
                if index > 0:
                    await asyncio.sleep(settings.ozon_enrich_delay_seconds)
                url = str(product.get("url") or "")
                if not url:
                    continue
                struct_logger.info(
                    "ozon_enrich_navigate",
                    query=query,
                    index=index + 1,
                    total=len(products),
                    url=url,
                )
                page_html, page_error = await ozon_browser.navigate_and_get_html(
                    browser,
                    url,
                    wait_seconds=settings.ozon_enrich_wait_seconds,
                    require_product_detail=True,
                )
                if page_error == "waf" or (page_html and ozon_browser.is_challenge(page_html)):
                    struct_logger.warning(
                        "ozon_enrich_waf_stop",
                        url=url,
                        index=index + 1,
                        message="Stopping enrich after captcha — returning search previews",
                    )
                    break
                if page_error or not page_html:
                    struct_logger.warning(
                        "ozon_enrich_fetch_error",
                        url=url,
                        error=page_error or "empty_html",
                    )
                    continue

                detail = extract_product_enrichment(page_html)
                _apply_enrichment(product, detail)
                struct_logger.info(
                    "ozon_enrich_success",
                    url=url,
                    has_description=bool(product.get("description")),
                    characteristics_count=len(product.get("characteristics") or {}),
                )

            return products, None

        products, error = await ozon_browser.run_browser_pipeline(
            query,
            pipeline,
        )
        if error or products is None:
            return _map_pipeline_error(error)

        if settings.ozon_browser_cache_enabled:
            from cache_manager import set_cached_products

            set_cached_products(
                cache_key,
                products,
                ttl=settings.ozon_browser_cache_ttl_seconds,
            )

        return products, None, None

    async def enrich_product(self, preview: dict[str, Any]) -> dict[str, Any]:
        """Standalone enrich — disabled by default; use search() previews in production."""
        product = _preview_to_product(preview)
        if not settings.ozon_enrich_enabled:
            return product
        url = str(product.get("url") or "")
        if not url:
            return product

        html, error = await ozon_browser.fetch_product_html(url)
        if error or not html or ozon_browser.is_challenge(html):
            struct_logger.warning("ozon_enrich_fetch_error", url=url, error=error or "challenge")
            return product

        detail = extract_product_enrichment(html)
        _apply_enrichment(product, detail)
        return product


parser = TwoStageOzonParser()
