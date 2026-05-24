from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urlparse

from other_public_scraper.config import DOMAIN_BLACKLIST, settings
from other_public_scraper.diagnostics import active_diagnostics, reset_diagnostics
from other_public_scraper.domain_strategies import listing_domain_key
from other_public_scraper.ml.query_classifier import classify_query
from other_public_scraper.models import MeiliProductDoc, OtherExtractResult, UrlCandidate
from other_public_scraper.pipelines.catalog_harvest import _extract_links, expand_listing_candidates
from other_public_scraper.pipelines.page_extractor import (
    extract_product_from_html,
    extract_products_from_listing_html,
    is_category_listing,
    is_product_page_url,
)
from other_public_scraper.pipelines.web_search import search_live_urls_expanded
from other_public_scraper.storage.meili import search_meili, upsert_products
from other_public_scraper.transport import fetch_html
from other_public_scraper.url_heuristics import (
    filter_and_sort_candidates,
    is_fetch_blocked,
    is_rejected_url,
    looks_like_listing_url,
    url_quality_score,
)

logger = logging.getLogger(__name__)

TIRES_RE = re.compile(r"\d{3}/\d{2}\s*R?\d{2}", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_BAD_TITLE_RE = re.compile(
    r"(?:"
    r"добавить\s+товар"
    r"|нет\s+в\s+наличии"
    r"|распродажа"
    r"|каталог"
    r")",
    re.IGNORECASE,
)

_QUERY_ALIASES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("трус",), ("трус", "боксер", "боксёр", "слип", "бриф")),
    (("очк",), ("очк", "оправ", "линз", "rayban", "ray-ban", "ray ban")),
    (("шин", "резин"), ("шин", "резин", "tyre", "tire")),
    (("мыш",), ("мыш", "mouse")),
    (("ноут",), ("ноут", "laptop", "notebook")),
    (("смартфон", "телефон", "iphone", "айфон"), ("смартфон", "телефон", "iphone", "айфон")),
)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_blacklisted(url: str) -> bool:
    domain = _domain(url)
    return domain in DOMAIN_BLACKLIST or any(b in domain for b in DOMAIN_BLACKLIST)


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


def _stem(token: str) -> str:
    token = token.lower().replace("ё", "е")
    if token.isdigit():
        return token
    return token[: max(3, min(len(token), len(token) - 1))]


def _query_needles(query: str) -> tuple[set[str], set[str]]:
    tokens = [
        _stem(token)
        for token in _WORD_RE.findall(query)
        if token.isdigit() or len(token) > 2
    ]
    numeric = {token for token in tokens if token.isdigit()}
    words = {token for token in tokens if not token.isdigit()}
    for triggers, aliases in _QUERY_ALIASES:
        if any(trigger in words for trigger in triggers):
            words.update(_stem(alias) for alias in aliases)
    return words, numeric


def _is_title_relevant_to_query(title: str, query: str) -> bool:
    title_lower = title.lower().replace("ё", "е")
    if _BAD_TITLE_RE.search(title_lower):
        return False
    words, numeric = _query_needles(query)
    if numeric and not all(number in title_lower for number in numeric):
        return False
    if not words:
        return True
    title_tokens = {_stem(token) for token in _WORD_RE.findall(title_lower)}
    return bool(words & title_tokens) or any(word in title_lower for word in words)


def _is_final_product_result(item: OtherExtractResult) -> bool:
    if looks_like_listing_url(item.product_url):
        return False
    return not is_category_listing(item.title, item.product_url)


def _cap_per_domain(
    products: list[OtherExtractResult],
    *,
    max_total: int,
    hard_cap_per_domain: int,
) -> list[OtherExtractResult]:
    """Return up to hard_cap_per_domain products from each domain, max_total overall."""
    if not products:
        return products

    sorted_products = sorted(
        products, key=lambda p: p.relevance_score, reverse=True
    )
    seen_per_domain: dict[str, int] = {}
    out: list[OtherExtractResult] = []
    for p in sorted_products:
        count = seen_per_domain.get(p.source_domain, 0)
        if count >= hard_cap_per_domain:
            continue
        seen_per_domain[p.source_domain] = count + 1
        out.append(p)
        if len(out) >= max_total:
            break
    return out


async def _fetch_and_extract(candidate: UrlCandidate, query: str) -> list[OtherExtractResult]:
    url_short = candidate.url[:90]
    use_meili_cache = (
        settings.other_meili_read_enabled
        and candidate.source == "meili"
        and candidate.cached_price_rub
        and candidate.cached_image_url
        and candidate.title
    )
    if use_meili_cache:
        if looks_like_listing_url(candidate.url) or is_category_listing(
            candidate.title, candidate.url
        ):
            active_diagnostics().extract_failed += 1
            active_diagnostics().note_failure(f"Meili: каталог, не товар — {url_short}")
            return []
        if not _is_title_relevant_to_query(candidate.title, query):
            active_diagnostics().extract_failed += 1
            active_diagnostics().note_failure(f"Meili: нерелевантно — {candidate.title[:50]}")
            return []
        active_diagnostics().extract_ok += 1
        return [
            OtherExtractResult(
                title=candidate.title,
                description=candidate.cached_description,
                price_rub=int(candidate.cached_price_rub),
                image_url=candidate.cached_image_url,
                product_url=candidate.url,
                source_domain=candidate.domain or _domain(candidate.url),
                confidence=1.0,
                extraction_method="meili_cache",
                relevance_score=max(candidate.similarity, 1.0),
            )
        ]

    result = await fetch_html(candidate.url)
    if result is None:
        active_diagnostics().fetch_failed += 1
        return []
    active_diagnostics().fetch_ok += 1

    listing = extract_products_from_listing_html(
        result.body,
        candidate.url,
        relevance_score=candidate.similarity,
        max_items=settings.other_listing_products_per_page,
    )
    if listing:
        accepted: list[OtherExtractResult] = []
        for extracted in listing:
            if not _is_final_product_result(extracted):
                continue
            if not _is_title_relevant_to_query(extracted.title, query):
                continue
            extracted.relevance_score = max(extracted.relevance_score, candidate.similarity)
            accepted.append(extracted)
        if accepted:
            active_diagnostics().extract_ok += len(accepted)
            return accepted

    extracted = extract_product_from_html(
        result.body,
        candidate.url,
        relevance_score=candidate.similarity,
    )
    if extracted is None:
        active_diagnostics().extract_failed += 1
        active_diagnostics().note_failure(f"Нет title/price/image — {url_short}")
        return []
    if not _is_final_product_result(extracted):
        active_diagnostics().extract_failed += 1
        active_diagnostics().note_failure(f"Страница каталога, не товар — {url_short}")
        return []
    if not _is_title_relevant_to_query(extracted.title, query):
        active_diagnostics().extract_failed += 1
        active_diagnostics().note_failure(f"Нерелевантно — {extracted.title[:50]}")
        return []
    extracted.relevance_score = max(extracted.relevance_score, candidate.similarity)
    active_diagnostics().extract_ok += 1
    return [extracted]


_LISTING_SLUGS = frozenset({
    "naushniki",
    "smartfony",
    "noutbuki",
    "planshety",
    "monitory",
    "shiny",
    "tyres",
    "tyre",
    "catalog.html",
    "iphone-15",
    "iphone-16",
})


def _is_listing_grid_url(url: str) -> bool:
    path = urlparse(url).path.lower().rstrip("/")
    if is_rejected_url(url) or is_product_page_url(url):
        return False
    segments = [part for part in path.split("/") if part]
    if not segments:
        return True
    if "catalog" in segments and len(segments) <= 4:
        return True
    if any(segment in _LISTING_SLUGS for segment in segments):
        return True
    if any(token in path for token in ("/smartfony/", "/iphone-", "/apple_iphone/", "/naushniki/")):
        return True
    # shallow category paths like /naushniki/ or /brand_apple/
    if len(segments) <= 2 and not segments[-1].isdigit():
        return True
    return False


def _listing_grid_priority(url: str) -> float:
    path = urlparse(url).path.lower().rstrip("/")
    score = 0.0
    if "/catalog/" in path:
        score += 1.0
    path_hints = ("/tyres", "/tyre", "/shiny", "season_", "/smartfony/", "/iphone-")
    if any(token in path for token in path_hints):
        score += 0.6
    segments = [part for part in path.split("/") if part]
    if len(segments) >= 3:
        score += 0.2
    host = _domain(url)
    if host == "dns-shop.ru" or host.endswith(".dns-shop.ru"):
        score += 0.3
    elif host == "technocity.ru" or host.endswith(".technocity.ru"):
        score += 1.0
    elif "e2e4online.ru" in host:
        score += 1.0
    elif host.endswith(".citilink.ru") or host == "citilink.ru":
        score += 0.6
    elif "technopark.ru" in host or host == "mvideo.ru":
        score += 0.4
    if any(token in path for token in ("/myshi", "/mysi", "/mouse", "mysh")):
        score += 0.7
    if "proizvoditel--" in path:
        score -= 0.4
    if "beeline.ru" in host or "blizko.ru" in host:
        score -= 0.6
    if not path:
        score -= 0.3
    return score


async def _resolve_listing_grid_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path:
        return url
    if is_fetch_blocked(url):
        return url
    result = await fetch_html(url)
    if result is None:
        return url
    _, catalogs = _extract_links(result.body, url)
    if not catalogs:
        return url
    catalogs.sort(key=_listing_grid_priority, reverse=True)
    return catalogs[0]


def _accept_listing_products(
    listing: list[OtherExtractResult],
    query: str,
    seen: set[str],
) -> list[OtherExtractResult]:
    accepted: list[OtherExtractResult] = []
    for extracted in listing:
        if not _is_final_product_result(extracted):
            continue
        if not _is_title_relevant_to_query(extracted.title, query):
            continue
        key = extracted.product_url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        accepted.append(extracted)
        active_diagnostics().extract_ok += 1
    return accepted


def _unique_domain_listing_candidates(candidates: list[UrlCandidate]) -> list[UrlCandidate]:
    grid_candidates = [c for c in candidates if _is_listing_grid_url(c.url)]
    grid_candidates.sort(key=lambda item: _listing_grid_priority(item.url), reverse=True)
    seen_domains: set[str] = set()
    unique: list[UrlCandidate] = []
    for candidate in grid_candidates:
        domain_key = listing_domain_key(candidate.url)
        if domain_key in seen_domains:
            continue
        seen_domains.add(domain_key)
        unique.append(candidate)
    return unique


async def _collect_listing_grid_products(
    candidates: list[UrlCandidate],
    query: str,
    *,
    max_pages: int = 5,
) -> list[OtherExtractResult]:
    grid_candidates = _unique_domain_listing_candidates(candidates)
    products: list[OtherExtractResult] = []
    seen: set[str] = set()
    for candidate in grid_candidates[:max_pages]:
        page_url = await _resolve_listing_grid_url(candidate.url)
        result = await fetch_html(page_url)
        if result is None:
            continue
        active_diagnostics().fetch_ok += 1
        listing = extract_products_from_listing_html(
            result.body,
            page_url,
            relevance_score=candidate.similarity,
            max_items=settings.other_listing_products_per_page,
        )
        accepted = _accept_listing_products(listing, query, seen)
        products.extend(accepted)
    products.sort(key=lambda item: item.relevance_score, reverse=True)
    return products


_FAST_LIMIT = 5
_FULL_LIMIT = settings.other_max_results


def _rank_search_candidates(candidates: list[UrlCandidate], *, limit: int) -> list[UrlCandidate]:
    """Simple mode: try product-looking URLs first, then everything else."""
    return sorted(candidates, key=lambda c: url_quality_score(c.url), reverse=True)[:limit]


async def _search_once(
    query: str, region: str, *, on_partial=None
) -> list[OtherExtractResult]:
    from app.core.regions import resolve_region

    region_obj = resolve_region(region)
    if region_obj.id != "moscow":
        geo_query = f"{query} {region_obj.name}".strip()
    else:
        geo_query = query

    diag = reset_diagnostics(query)
    t0 = time.perf_counter()
    category = classify_query(query)
    logger.info(
        "other_search_start query=%r geo_query=%r region=%s category=%s",
        query,
        geo_query,
        region,
        category,
    )

    live_hits = await search_live_urls_expanded(
        geo_query,
        limit=max(settings.other_max_searxng_urls, settings.other_max_results * 3),
        category=category,
    )
    if not live_hits and geo_query != query:
        logger.info("other_search_geo_empty query=%r geo_query=%r retry_plain", query, geo_query)
        live_hits = await search_live_urls_expanded(
            query,
            limit=max(settings.other_max_searxng_urls, settings.other_max_results * 3),
            category=category,
        )
    diag.live_urls = len(live_hits)
    diag.live_sample = [c.url[:90] for c in live_hits[:5]]
    meili_hits: list[UrlCandidate] = []
    if settings.other_meili_read_enabled:
        meili_hits = await search_meili(query, limit=10)
    diag.meili_hits = len(meili_hits)
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
    diag.candidates_merged = len(candidates)

    candidates.sort(key=lambda c: url_quality_score(c.url), reverse=True)
    grid_products: list[OtherExtractResult] = []
    if category != "unknown":
        grid_products = await _collect_listing_grid_products(candidates, query)

    harvested_candidates = candidates
    if candidates and len(grid_products) < settings.other_max_results:
        try:
            harvested_candidates = await asyncio.wait_for(
                expand_listing_candidates(
                    candidates,
                    per_listing=settings.other_max_per_domain,
                    max_listings=settings.other_max_results,
                ),
                timeout=settings.other_catalog_harvest_budget_seconds,
            )
        except TimeoutError:
            logger.warning(
                "other_catalog_harvest_timeout query=%r budget=%.0fs",
                query,
                settings.other_catalog_harvest_budget_seconds,
            )
            diag.timed_out = True

    candidates = filter_and_sort_candidates(harvested_candidates)

    if len(grid_products) < settings.other_max_results:
        extra_grid = await _collect_listing_grid_products(candidates, query)
        seen_grid = {item.product_url.split("#")[0] for item in grid_products}
        for item in extra_grid:
            key = item.product_url.split("#")[0]
            if key in seen_grid:
                continue
            seen_grid.add(key)
            grid_products.append(item)

    # Accumulate products starting from grid results
    products: list[OtherExtractResult] = []
    seen_product_urls: set[str] = set()
    seen_per_domain: dict[str, int] = {}

    def _append_product(item: OtherExtractResult) -> bool:
        if not _is_final_product_result(item):
            return False
        if not _is_title_relevant_to_query(item.title, query):
            return False
        key = item.product_url.split("#")[0]
        if key in seen_product_urls:
            return False
        count = seen_per_domain.get(item.source_domain, 0)
        if count >= settings.other_max_per_domain:
            return False
        seen_product_urls.add(key)
        seen_per_domain[item.source_domain] = count + 1
        products.append(item)
        return True

    for item in grid_products:
        _append_product(item)
        if len(products) >= settings.other_max_results:
            break

    ranked: list = []
    skipped = 0
    fast_published = False

    if len(products) < settings.other_max_results:
        rank_pool = min(settings.other_rank_pool_size, len(candidates))
        ranked = _rank_search_candidates(candidates, limit=rank_pool)
        if not ranked and candidates:
            logger.info(
                "other_search_rank_fallback query=%r using_unfiltered=%d",
                query,
                min(rank_pool, len(candidates)),
            )
        else:
            logger.info("other_search_ranked query=%r ranked=%d", query, len(ranked))
        diag.candidates_ranked = len(ranked)

        tasks = [
            asyncio.create_task(_fetch_and_extract(candidate, query))
            for candidate in ranked
        ]

        for fut in asyncio.as_completed(tasks):
            try:
                group = await fut
            except asyncio.CancelledError:
                skipped += 1
                continue
            except Exception:
                skipped += 1
                continue

            if not group:
                skipped += 1

            for item in group:
                if not _append_product(item):
                    skipped += 1

            if on_partial and not fast_published and len(products) >= _FAST_LIMIT:
                try:
                    partial_sorted = sorted(
                        products, key=lambda p: p.relevance_score, reverse=True
                    )
                    await on_partial(partial_sorted[:_FAST_LIMIT])
                except Exception:
                    pass
                fast_published = True

            if len(products) >= _FULL_LIMIT:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                break

    if category == "unknown":
        extra_grid = await _collect_listing_grid_products(candidates, query, max_pages=3)
        for item in extra_grid:
            _append_product(item)
            if len(products) >= settings.other_max_results:
                break

    # If grid alone had enough, try fast partial from grid
    if on_partial and not fast_published and products:
        try:
            partial_sorted = sorted(products, key=lambda p: p.relevance_score, reverse=True)
            await on_partial(partial_sorted[:_FAST_LIMIT])
        except Exception:
            pass

    hard_cap_per_domain = settings.other_max_per_domain

    products = [item for item in products if _is_final_product_result(item)]

    products = _cap_per_domain(
        products,
        max_total=settings.other_max_results,
        hard_cap_per_domain=hard_cap_per_domain,
    )

    logger.info(
        "other_search_done query=%r extracted=%d skipped=%d took_ms=%d",
        query,
        len(products),
        skipped,
        int((time.perf_counter() - t0) * 1000),
    )
    if not products and ranked:
        logger.warning(
            "other_search_zero_results query=%r tried=%d fetch/extract/filter failed",
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
        try:
            await upsert_products(docs)
        except Exception as exc:
            logger.warning("other_meili_upsert_failed count=%d error=%s", len(docs), exc)

    return products


async def search_other(
    query: str, region: str = "moscow", *, on_partial=None
) -> list[OtherExtractResult]:
    query = query.strip()
    if not query:
        return []
    try:
        return await asyncio.wait_for(
            _search_once(query, region, on_partial=on_partial),
            timeout=settings.other_search_timeout_seconds,
        )
    except TimeoutError:
        diag = active_diagnostics()
        diag.timed_out = True
        logger.warning("other search timeout query=%r", query)
        return []
