from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urlparse

from other_public_scraper.config import (
    CLOTHES_NEGATIVE,
    DOMAIN_BLACKLIST,
    ORGTECH_BRANDS,
    settings,
)
from other_public_scraper.ml.query_classifier import classify_query
from other_public_scraper.ml.relevance_filter import cosine_similarity_batch, rank_candidates
from other_public_scraper.models import MeiliProductDoc, OtherExtractResult, UrlCandidate
from other_public_scraper.pipelines.page_extractor import extract_product_from_html
from other_public_scraper.pipelines.web_search import search_live_urls
from other_public_scraper.storage.meili import search_meili, upsert_products
from other_public_scraper.transport import fetch_html

logger = logging.getLogger(__name__)

TIRES_RE = re.compile(r"\d{3}/\d{2}\s*R?\d{2}", re.IGNORECASE)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_blacklisted(url: str) -> bool:
    domain = _domain(url)
    return domain in DOMAIN_BLACKLIST or any(b in domain for b in DOMAIN_BLACKLIST)


def _passes_category_sanity(title: str, query: str, category: str) -> bool:
    title_lower = title.lower()
    query_lower = query.lower()
    if category == "tires":
        return bool(TIRES_RE.search(title) or TIRES_RE.search(query))
    if category == "orgtech":
        if any(brand in title_lower or brand in query_lower for brand in ORGTECH_BRANDS):
            return True
        generic = ("ноутбук", "принтер", "монитор", "клавиатура", "мыш", "компьютер")
        return any(word in title_lower or word in query_lower for word in generic)
    if category == "clothes":
        return not any(word in title_lower for word in CLOTHES_NEGATIVE)
    return True


def _merge_candidates(*groups: list[UrlCandidate]) -> list[UrlCandidate]:
    merged: dict[str, UrlCandidate] = {}
    for group in groups:
        for item in group:
            if _is_blacklisted(item.url):
                continue
            key = item.url.split("#")[0]
            if key not in merged:
                merged[key] = item
    return list(merged.values())


async def _fetch_and_extract(
    candidate: UrlCandidate, query: str, category: str
) -> OtherExtractResult | None:
    url_short = candidate.url[:90]
    use_meili_cache = (
        settings.other_meili_read_enabled
        and candidate.source == "meili"
        and candidate.cached_price_rub
        and candidate.cached_image_url
        and candidate.title
    )
    if use_meili_cache:
        title_sim = cosine_similarity_batch(query, candidate.title)
        if title_sim < settings.other_title_similarity_threshold:
            logger.info(
                "other_extract_skip reason=meili_low_similarity url=%s sim=%.3f threshold=%.2f",
                url_short,
                title_sim,
                settings.other_title_similarity_threshold,
            )
            return None
        if not _passes_category_sanity(candidate.title, query, category):
            logger.info(
                "other_extract_skip reason=meili_category_sanity url=%s category=%s title=%r",
                url_short,
                category,
                candidate.title[:60],
            )
            return None
        logger.info(
            "other_extract_ok method=meili_cache url=%s title=%r price=%d",
            url_short,
            candidate.title[:60],
            candidate.cached_price_rub,
        )
        return OtherExtractResult(
            title=candidate.title,
            description=candidate.cached_description,
            price_rub=int(candidate.cached_price_rub),
            image_url=candidate.cached_image_url,
            product_url=candidate.url,
            source_domain=candidate.domain or _domain(candidate.url),
            confidence=1.0,
            extraction_method="meili_cache",
            relevance_score=title_sim,
        )

    result = await fetch_html(candidate.url)
    if result is None:
        return None
    extracted = extract_product_from_html(
        result.body,
        candidate.url,
        relevance_score=candidate.similarity,
    )
    if extracted is None:
        logger.info(
            "other_extract_skip reason=no_title_price_image url=%s source=%s",
            url_short,
            candidate.source,
        )
        return None
    title_sim = cosine_similarity_batch(query, extracted.title)
    if title_sim < settings.other_title_similarity_threshold:
        logger.info(
            "other_extract_skip reason=low_title_similarity url=%s sim=%.3f title=%r",
            url_short,
            title_sim,
            extracted.title[:60],
        )
        return None
    if not _passes_category_sanity(extracted.title, query, category):
        logger.info(
            "other_extract_skip reason=category_sanity url=%s category=%s title=%r",
            url_short,
            category,
            extracted.title[:60],
        )
        return None
    extracted.relevance_score = title_sim
    logger.info(
        "other_extract_ok method=%s url=%s title=%r price=%d sim=%.3f",
        extracted.extraction_method,
        url_short,
        extracted.title[:60],
        extracted.price_rub,
        title_sim,
    )
    return extracted


async def _search_once(query: str, region: str) -> list[OtherExtractResult]:
    _ = region
    t0 = time.perf_counter()
    category = classify_query(query)
    logger.info("other_search_start query=%r region=%s category=%s", query, region, category)

    live_hits = await search_live_urls(query, limit=settings.other_max_searxng_urls)
    meili_hits: list[UrlCandidate] = []
    if settings.other_meili_read_enabled:
        meili_hits = await search_meili(query, limit=10)
    logger.info(
        "other_search_sources query=%r meili=%d live=%d meili_read=%s",
        query,
        len(meili_hits),
        len(live_hits),
        settings.other_meili_read_enabled,
    )
    if live_hits:
        logger.info(
            "other_live_sample query=%r urls=%s",
            query,
            [c.url[:70] for c in live_hits[:5]],
        )

    candidates = _merge_candidates(meili_hits, live_hits)
    logger.info("other_search_merged query=%r candidates=%d", query, len(candidates))

    ranked = rank_candidates(
        query,
        candidates,
        threshold=settings.other_snippet_similarity_threshold,
        limit=8,
    )
    if not ranked and candidates:
        logger.info(
            "other_search_rank_fallback query=%r using_unfiltered=%d",
            query,
            min(8, len(candidates)),
        )
        ranked = sorted(candidates, key=lambda c: c.title, reverse=False)[:8]
    else:
        logger.info("other_search_ranked query=%r ranked=%d", query, len(ranked))

    fetched = await asyncio.gather(
        *[_fetch_and_extract(candidate, query, category) for candidate in ranked]
    )
    products = [item for item in fetched if item is not None]
    skipped = len(ranked) - len(products)
    products.sort(key=lambda p: p.relevance_score, reverse=True)
    products = products[: settings.other_max_results]

    logger.info(
        "other_search_done query=%r extracted=%d skipped=%d took_ms=%d",
        query,
        len(products),
        skipped,
        int((time.perf_counter() - t0) * 1000),
    )
    if not products and ranked:
        logger.warning(
            "other_search_zero_results query=%r tried=%d — все URL отфалились на fetch/extract/filter",
            query,
            len(ranked),
        )

    docs = [
        MeiliProductDoc(
            id=f"{item.source_domain}_{hash(item.product_url) & 0xFFFFFFFF}",
            url=item.product_url,
            domain=item.source_domain,
            title=item.title,
            category=category,
            image_url=item.image_url,
            last_price=item.price_rub * 100,
            confidence=item.confidence,
        )
        for item in products
    ]
    if docs:
        await upsert_products(docs)

    return products


async def search_other(query: str, region: str = "moscow") -> list[OtherExtractResult]:
    query = query.strip()
    if not query:
        return []
    try:
        return await asyncio.wait_for(
            _search_once(query, region),
            timeout=settings.other_search_timeout_seconds,
        )
    except TimeoutError:
        logger.warning("other search timeout query=%r", query)
        return []
