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
from other_public_scraper.diagnostics import active_diagnostics, reset_diagnostics
from other_public_scraper.ml.query_classifier import classify_query
from other_public_scraper.ml.relevance_filter import cosine_similarity_batch, rank_candidates
from other_public_scraper.models import MeiliProductDoc, OtherExtractResult, UrlCandidate
from other_public_scraper.optics_seeds import optics_seed_candidates
from other_public_scraper.orgtech_seeds import orgtech_seed_candidates
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
    url_quality_score,
)

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
        return bool(TIRES_RE.search(title) or TIRES_RE.search(query) or "шин" in query_lower)
    if category == "orgtech":
        if any(brand in title_lower or brand in query_lower for brand in ORGTECH_BRANDS):
            return True
        generic = (
            "ноутбук",
            "принтер",
            "монитор",
            "клавиатура",
            "мыш",
            "компьютер",
            "айфон",
            "iphone",
            "смартфон",
            "smartfon",
            "телефон",
        )
        return any(word in title_lower or word in query_lower for word in generic)
    if category == "clothes":
        return not any(word in title_lower for word in CLOTHES_NEGATIVE)
    return True


def _is_title_relevant(title: str, query: str, category: str) -> bool:
    title_sim = cosine_similarity_batch(query, title)
    if title_sim >= settings.other_title_similarity_threshold:
        return True
    query_lower = query.lower()
    if category == "tires" or "шин" in query_lower or "резин" in query_lower:
        if TIRES_RE.search(title) or TIRES_RE.search(query) or "шин" in query_lower:
            return True
    if category == "orgtech":
        generic = (
            "ноутбук",
            "принтер",
            "монитор",
            "клавиатура",
            "мыш",
            "компьютер",
            "айфон",
            "iphone",
        )
        title_lower = title.lower()
        if any(word in title_lower or word in query_lower for word in generic):
            return True
    if re.search(r"очк", query_lower):
        optics_terms = ("очк", "оправ", "ray-ban", "ray ban", "диоптр", "linz", "линз", "optik", "оптик")
        if any(term in title.lower() for term in optics_terms):
            return True
    return False


def _title_relevance_score(title: str, query: str, category: str) -> float:
    title_sim = cosine_similarity_batch(query, title)
    if _is_title_relevant(title, query, category):
        return max(title_sim, settings.other_title_similarity_threshold)
    return title_sim


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


def _cap_per_domain(
    products: list[OtherExtractResult],
    *,
    max_total: int,
    hard_cap_per_domain: int,
) -> list[OtherExtractResult]:
    """
    Диверсификация результатов по source_domain.

    - Один домен в результатах → возвращаем как есть (top max_total
      по relevance_score). Иначе обрезали бы единственный доступный
      источник без альтернатив.
    - Несколько доменов → не более hard_cap_per_domain с каждого,
      сначала самые релевантные.

    Returns: список, отсортированный по relevance_score убыв.,
    длиной до max_total.
    """
    if not products:
        return products

    sorted_products = sorted(
        products, key=lambda p: p.relevance_score, reverse=True
    )
    domains = {p.source_domain for p in sorted_products}
    if len(domains) <= 1:
        return sorted_products[:max_total]

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


async def _fetch_and_extract(
    candidate: UrlCandidate, query: str, category: str
) -> list[OtherExtractResult]:
    url_short = candidate.url[:90]
    use_meili_cache = (
        settings.other_meili_read_enabled
        and candidate.source == "meili"
        and candidate.cached_price_rub
        and candidate.cached_image_url
        and candidate.title
    )
    if use_meili_cache:
        title_sim = _title_relevance_score(candidate.title, query, category)
        if not _is_title_relevant(candidate.title, query, category):
            active_diagnostics().note_failure(
                f"Meili: низкая релевантность {title_sim:.2f} — {url_short}"
            )
            active_diagnostics().extract_failed += 1
            return []
        if not _passes_category_sanity(candidate.title, query, category):
            active_diagnostics().extract_failed += 1
            active_diagnostics().note_failure(f"Категория не прошла проверку — {url_short}")
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
                relevance_score=title_sim,
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
            if not _is_title_relevant(extracted.title, query, category):
                continue
            if not _passes_category_sanity(extracted.title, query, category):
                continue
            extracted.relevance_score = _title_relevance_score(extracted.title, query, category)
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
    if is_category_listing(extracted.title, extracted.product_url):
        active_diagnostics().extract_failed += 1
        active_diagnostics().note_failure(f"Страница каталога, не товар — {url_short}")
        return []
    title_sim = _title_relevance_score(extracted.title, query, category)
    if not _is_title_relevant(extracted.title, query, category):
        active_diagnostics().extract_failed += 1
        active_diagnostics().note_failure(
            f"Низкая релевантность {title_sim:.2f} — {extracted.title[:50]}"
        )
        return []
    if not _passes_category_sanity(extracted.title, query, category):
        active_diagnostics().extract_failed += 1
        active_diagnostics().note_failure(f"Категория не прошла проверку — {extracted.title[:50]}")
        return []
    extracted.relevance_score = title_sim
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
    category: str,
    seen: set[str],
) -> list[OtherExtractResult]:
    accepted: list[OtherExtractResult] = []
    for extracted in listing:
        if not _is_title_relevant(extracted.title, query, category):
            continue
        if not _passes_category_sanity(extracted.title, query, category):
            continue
        key = extracted.product_url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        extracted.relevance_score = _title_relevance_score(extracted.title, query, category)
        accepted.append(extracted)
        active_diagnostics().extract_ok += 1
    if accepted:
        return accepted
    for extracted in sorted(listing, key=lambda item: item.relevance_score, reverse=True):
        if not _passes_category_sanity(extracted.title, query, category):
            continue
        if is_category_listing(extracted.title, extracted.product_url):
            continue
        key = extracted.product_url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        extracted.relevance_score = max(
            extracted.relevance_score,
            settings.other_title_similarity_threshold,
        )
        accepted.append(extracted)
        active_diagnostics().extract_ok += 1
        break
    return accepted


def _unique_domain_listing_candidates(candidates: list[UrlCandidate]) -> list[UrlCandidate]:
    grid_candidates = [c for c in candidates if _is_listing_grid_url(c.url)]
    grid_candidates.sort(key=lambda item: _listing_grid_priority(item.url), reverse=True)
    seen_domains: set[str] = set()
    unique: list[UrlCandidate] = []
    for candidate in grid_candidates:
        domain = _domain(candidate.url)
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        unique.append(candidate)
    return unique


async def _collect_listing_grid_products(
    candidates: list[UrlCandidate],
    query: str,
    category: str,
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
        accepted = _accept_listing_products(listing, query, category, seen)
        products.extend(accepted)
        if products:
            break
    products.sort(key=lambda item: item.relevance_score, reverse=True)
    return products


_FAST_LIMIT = 5
_FULL_LIMIT = settings.other_max_results


async def _search_once(
    query: str, region: str, *, on_partial=None
) -> list[OtherExtractResult]:
    from app.core.regions import resolve_region

    region_obj = resolve_region(region)
    if region_obj.id != "moscow":
        geo_query = f"{query} {region_obj.search_keyword} доставка".strip()
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
        limit=settings.other_max_searxng_urls,
        category=category,
    )
    if category == "orgtech" and len(live_hits) < 4:
        live_hits = _merge_candidates(live_hits, orgtech_seed_candidates(query))
    if re.search(r"очк", query, re.IGNORECASE) and len(live_hits) < 6:
        live_hits = _merge_candidates(live_hits, optics_seed_candidates(query))
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
    grid_products = await _collect_listing_grid_products(candidates, query, category)
    
    harvested_candidates = candidates
    if grid_products and len(grid_products) < settings.other_max_results:
        try:
            harvested_candidates = await asyncio.wait_for(
                expand_listing_candidates(candidates),
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

    if grid_products and len(grid_products) < settings.other_max_results:
        extra_grid = await _collect_listing_grid_products(candidates, query, category)
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
    for item in grid_products:
        key = item.product_url.split("#")[0]
        seen_product_urls.add(key)
        products.append(item)

    ranked: list = []
    skipped = 0
    fast_published = False

    if len(products) < settings.other_max_results:
        rank_pool = min(settings.other_rank_pool_size, len(candidates))
        ranked = rank_candidates(
            query,
            candidates,
            threshold=settings.other_snippet_similarity_threshold,
            limit=rank_pool,
        )
        if not ranked and candidates:
            logger.info(
                "other_search_rank_fallback query=%r using_unfiltered=%d",
                query,
                min(rank_pool, len(candidates)),
            )
            ranked = sorted(
                candidates, key=lambda c: url_quality_score(c.url), reverse=True
            )[:rank_pool]
        elif len(ranked) < rank_pool and candidates:
            seen_urls = {c.url for c in ranked}
            for candidate in sorted(
                candidates, key=lambda c: url_quality_score(c.url), reverse=True
            ):
                if candidate.url in seen_urls:
                    continue
                ranked.append(candidate)
                seen_urls.add(candidate.url)
                if len(ranked) >= rank_pool:
                    break
        else:
            logger.info("other_search_ranked query=%r ranked=%d", query, len(ranked))
        diag.candidates_ranked = len(ranked)

        tasks = [
            asyncio.create_task(_fetch_and_extract(candidate, query, category))
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
                key = item.product_url.split("#")[0]
                if key in seen_product_urls:
                    continue
                seen_product_urls.add(key)
                products.append(item)

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

    # If grid alone had enough, try fast partial from grid
    if on_partial and not fast_published and products:
        try:
            partial_sorted = sorted(products, key=lambda p: p.relevance_score, reverse=True)
            await on_partial(partial_sorted[:_FAST_LIMIT])
        except Exception:
            pass

    products = _cap_per_domain(
        products,
        max_total=settings.other_max_results,
        hard_cap_per_domain=settings.other_max_per_domain,
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
        await upsert_products(docs)

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
