"""Offline job: rebuild Meilisearch index from Ozon sitemap."""

from __future__ import annotations

import asyncio

from ozon_public_scraper.logging_config import setup_logging
from ozon_public_scraper.pipelines.sitemap import rebuild_from_sitemap
from ozon_public_scraper.storage.meili import ensure_index, upsert_products


async def main() -> None:
    setup_logging()
    await ensure_index()
    products = await rebuild_from_sitemap(max_products=5000)
    if not products:
        print("No products collected — sitemap may be blocked (403). Check logs.")
        return
    count = await upsert_products(products)
    print(f"Indexed {count} products into Meilisearch")


if __name__ == "__main__":
    asyncio.run(main())
