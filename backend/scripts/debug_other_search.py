#!/usr/bin/env python3
"""Пошаговая диагностика 4-го источника (other). Запуск:

  cd backend && uv run python -m scripts.debug_other_search "ноутбук"
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

QUERY = sys.argv[1] if len(sys.argv) > 1 else "ноутбук"
REGION = sys.argv[2] if len(sys.argv) > 2 else "moscow"


async def main() -> None:
    from app.core.models import SearchRequest
    from app.sources.other.search import search_other_sources

    print(f"\n=== Диагностика other: query={QUERY!r} region={REGION} ===\n")
    request = SearchRequest(query=QUERY, region=REGION)
    products = await search_other_sources(request, original_query=QUERY)
    print(f"\n=== Итог: {len(products)} товаров ===")
    for p in products[:5]:
        print(f"  • [{p.source_domain}] {p.title[:60]} — {p.price // 100} ₽")


if __name__ == "__main__":
    asyncio.run(main())
