from __future__ import annotations

import argparse
import asyncio
import io
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from other_public_scraper.config import settings
from other_public_scraper.ml.query_classifier import classify_query
from other_public_scraper.models import MeiliProductDoc
from other_public_scraper.pipelines.page_extractor import extract_product_from_html
from other_public_scraper.storage.meili import ensure_index, upsert_products
from other_public_scraper.transport import fetch_html

logger = logging.getLogger(__name__)

PRODUCT_URL_RE = re.compile(r"/product/", re.IGNORECASE)
PRODUCT_SITEMAP_RE = re.compile(r"product", re.IGNORECASE)


def _parse_locs(xml_text: str, *, limit: int | None = None) -> list[str]:
    locs: list[str] = []
    try:
        stream = io.BytesIO(xml_text.encode("utf-8", errors="ignore"))
        for _event, elem in ET.iterparse(stream, events=("end",)):
            tag = elem.tag.split("}")[-1]
            if tag == "loc" and elem.text:
                locs.append(elem.text.strip())
                if limit is not None and len(locs) >= limit:
                    elem.clear()
                    break
            elem.clear()
    except ET.ParseError as exc:
        logger.warning("sitemap parse error (partial): %s", exc)
    return locs


async def _fetch_sitemap_urls(domain: str, limit: int) -> list[str]:
    index_url = f"https://www.{domain}/sitemap.xml" if not domain.startswith("www.") else f"https://{domain}/sitemap.xml"
    if not index_url.startswith("https://www.") and "://" not in domain:
        index_url = f"https://{domain}/sitemap.xml"

    result = await fetch_html(f"https://{domain.replace('www.', '')}/sitemap.xml")
    if result is None:
        result = await fetch_html(f"https://www.{domain.replace('www.', '')}/sitemap.xml")
    if result is None:
        return []

    locs = _parse_locs(result.body)
    product_sitemaps = [loc for loc in locs if PRODUCT_SITEMAP_RE.search(loc)]
    candidate_pages = [loc for loc in locs if PRODUCT_URL_RE.search(loc)]

    urls: list[str] = []
    seen: set[str] = set()

    def _add(url: str) -> None:
        if len(urls) >= limit:
            return
        host = urlparse(url).netloc.lower().replace("www.", "")
        if domain.replace("www.", "") not in host:
            return
        if not PRODUCT_URL_RE.search(url):
            return
        if url in seen:
            return
        seen.add(url)
        urls.append(url)

    for page in candidate_pages:
        _add(page)

    for sitemap_url in product_sitemaps[:3]:
        if len(urls) >= limit:
            break
        child = await fetch_html(sitemap_url)
        if child is None:
            continue
        for loc in _parse_locs(child.body, limit=limit * 3):
            _add(loc)
            if len(urls) >= limit:
                break

    return urls[:limit]


async def build_index(domains: list[str], max_per_domain: int) -> int:
    ensure_index()
    total = 0
    for domain in domains:
        urls = await _fetch_sitemap_urls(domain, max_per_domain)
        logger.info("domain=%s sitemap_urls=%d", domain, len(urls))
        docs: list[MeiliProductDoc] = []
        for url in urls:
            page = await fetch_html(url)
            if page is None:
                continue
            extracted = extract_product_from_html(page.body, url)
            if extracted is None:
                continue
            category = classify_query(extracted.title)
            docs.append(
                MeiliProductDoc(
                    id=f"{extracted.source_domain}_{hash(url) & 0xFFFFFFFF}",
                    url=url,
                    domain=extracted.source_domain,
                    title=extracted.title,
                    category=category,
                    image_url=extracted.image_url,
                    last_price=extracted.price_rub * 100,
                    confidence=extracted.confidence,
                )
            )
        if docs:
            total += await upsert_products(docs)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--domains", default=settings.other_precrawl_domains)
    parser.add_argument(
        "--max-per-domain", type=int, default=settings.other_precrawl_max_per_domain
    )
    args = parser.parse_args()
    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    count = asyncio.run(build_index(domains, args.max_per_domain))
    print(f"indexed {count} documents")


if __name__ == "__main__":
    main()
