from __future__ import annotations

import logging
import time

from meilisearch_python_sdk import Client
from meilisearch_python_sdk.errors import MeilisearchApiError

from other_public_scraper.config import settings
from other_public_scraper.models import MeiliProductDoc, UrlCandidate

logger = logging.getLogger(__name__)


def _client() -> Client:
    return Client(settings.meilisearch_url, settings.meilisearch_api_key or None)


def ensure_index() -> None:
    client = _client()
    try:
        client.get_index(settings.meilisearch_index)
    except MeilisearchApiError:
        client.create_index(settings.meilisearch_index, primary_key="id")
        index = client.index(settings.meilisearch_index)
        index.update_searchable_attributes(["title", "domain", "keywords", "url"])
        index.update_filterable_attributes(["category", "domain"])
        logger.info("created meili index %s", settings.meilisearch_index)


async def search_meili(query: str, *, limit: int = 10) -> list[UrlCandidate]:
    t0 = time.perf_counter()
    client = _client()
    try:
        result = client.index(settings.meilisearch_index).search(query, limit=limit)
    except Exception as exc:
        logger.warning("other meili search failed: %s", exc)
        return []

    hits: list[UrlCandidate] = []
    for hit in result.hits or []:
        if not isinstance(hit, dict):
            continue
        url = str(hit.get("url") or "")
        title = str(hit.get("title") or "")
        if not url:
            continue
        hits.append(
            UrlCandidate(
                url=url,
                domain=str(hit.get("domain") or ""),
                title=title,
                snippet=title,
                source="meili",
                category=hit.get("category"),
                cached_price_rub=int(hit["last_price"]) // 100 if hit.get("last_price") else None,
                cached_image_url=str(hit.get("image_url") or ""),
            )
        )

    logger.info(
        "other_meili query=%r results=%d latency_ms=%d",
        query,
        len(hits),
        int((time.perf_counter() - t0) * 1000),
    )
    return hits


async def upsert_products(docs: list[MeiliProductDoc]) -> int:
    if not docs:
        return 0
    ensure_index()
    client = _client()
    payload = [doc.model_dump(mode="json") for doc in docs]
    task = client.index(settings.meilisearch_index).add_documents(payload)
    client.wait_for_task(task.task_uid, timeout_in_ms=30_000)
    return len(payload)
