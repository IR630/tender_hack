from __future__ import annotations

import time

from meilisearch_python_sdk import Client
from meilisearch_python_sdk.errors import MeilisearchApiError

from ozon_public_scraper.config import settings
from ozon_public_scraper.logging_config import get_logger
from ozon_public_scraper.models import ProductUrl

logger = get_logger("ozon_public.storage.meili")


def _client() -> Client:
    return Client(settings.meilisearch_url, settings.meilisearch_api_key or None)


async def ensure_index() -> None:
    client = _client()
    try:
        client.get_index(settings.meilisearch_index)
    except MeilisearchApiError:
        client.create_index(settings.meilisearch_index, primary_key="id")
        index = client.index(settings.meilisearch_index)
        index.update_searchable_attributes(["slug", "url"])
        index.update_filterable_attributes(["category"])
        logger.info("meilisearch_index_created", context={"index": settings.meilisearch_index})


async def upsert_products(products: list[ProductUrl]) -> int:
    if not products:
        return 0
    client = _client()
    docs = [
        {
            "id": p.numeric_id,
            "url": str(p.url),
            "slug": p.slug,
            "category": p.category,
        }
        for p in products
    ]
    task = client.index(settings.meilisearch_index).add_documents(docs)
    logger.info("meilisearch_upsert", context={"count": len(docs), "task_uid": task.task_uid})
    return len(docs)


async def search_products(query: str, *, limit: int) -> tuple[list[ProductUrl], int]:
    t0 = time.perf_counter()
    client = _client()
    try:
        result = client.index(settings.meilisearch_index).search(query, limit=limit)
    except Exception as exc:
        logger.warning("meilisearch_search_failed", context={"error": str(exc)})
        return [], 0

    latency_ms = int((time.perf_counter() - t0) * 1000)
    hits: list[ProductUrl] = []
    for hit in result.hits or []:
        if not isinstance(hit, dict):
            continue
        numeric_id = str(hit.get("id", ""))
        slug = str(hit.get("slug", ""))
        url = hit.get("url")
        if numeric_id and url:
            hits.append(
                ProductUrl(
                    numeric_id=numeric_id,
                    slug=slug,
                    url=url,
                    category=hit.get("category"),
                )
            )

    logger.info(
        "meilisearch_query",
        context={"query": query, "results_count": len(hits), "latency_ms": latency_ms},
    )
    return hits, latency_ms


async def delete_product(numeric_id: str) -> None:
    client = _client()
    try:
        client.index(settings.meilisearch_index).delete_document(numeric_id)
        logger.info("meilisearch_deleted", context={"id": numeric_id})
    except Exception as exc:
        logger.warning("meilisearch_delete_failed", context={"id": numeric_id, "error": str(exc)})
