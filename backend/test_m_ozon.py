import asyncio
import json
from pathlib import Path

from parser_ozon import OzonParser


async def main() -> None:
    parser = OzonParser(
        results_dir=Path("results/test_m_ozon"),
        demo_cache_path=Path("ozon_demo_cache.json"),
    )
    try:
        result = await parser.search("футболка мужская хлопок", use_cache=False)
    finally:
        await parser.close()

    print(
        json.dumps(
            {
                "query": result.query,
                "status": result.status,
                "method_used": result.method_used,
                "is_cached": result.is_cached,
                "products_found": len(result.products),
                "blocked_reason": result.blocked_reason,
                "attempts": [
                    {
                        "method": attempt.method,
                        "status": attempt.status,
                        "http_status": attempt.http_status,
                        "products_found": attempt.products_found,
                        "error": attempt.error,
                        "notes": attempt.notes,
                    }
                    for attempt in result.attempts
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
