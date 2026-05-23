from pathlib import Path

from app.core.config import settings
from app.core.models import Product, SearchRequest
from app.scrapers.base import BaseScraper
from parser_ozon import OzonParser, ParsedProduct, SearchResult

_ROOT_DIR = Path(__file__).resolve().parents[2]

_parser = OzonParser(
    results_dir=_ROOT_DIR / "results",
    timeout_seconds=settings.scraper_timeout_seconds,
    max_results=12,
    demo_cache_path=settings.ozon_demo_cache_path or _ROOT_DIR / "ozon_demo_cache.json",
    demo_fallback_enabled=settings.ozon_demo_fallback_enabled,
)


class OzonScraper(BaseScraper):
    source = "ozon"
    source_domain = "ozon.ru"

    def _to_product(self, item: ParsedProduct) -> Product:
        return Product(
            source="ozon",
            source_domain=self.source_domain,
            title=item.title,
            description=item.description,
            price=item.price or 0,
            currency="RUB",
            image_url=item.image_url,
            product_url=item.product_url,
            characteristics=item.characteristics,
            rating=item.rating,
            reviews_count=item.reviews_count,
            relevance_score=item.relevance_score,
            confidence=item.confidence,
        )

    def _build_meta(self, result: SearchResult) -> dict[str, str | None]:
        if result.is_cached:
            return {
                "status": "cached",
                "notice": "Live-поиск Ozon недоступен. Показаны кэшированные данные.",
                "cache_timestamp": result.cached_at,
            }
        if result.products:
            if result.cache_hit:
                return {
                    "status": "cached",
                    "notice": "Показаны сохраненные результаты Ozon.",
                    "cache_timestamp": result.cached_at,
                }
            return {"status": "live", "notice": None, "cache_timestamp": None}
        return {
            "status": "temporarily_unavailable",
            "notice": "Live-поиск Ozon временно недоступен.",
            "cache_timestamp": None,
        }

    async def search_with_meta(
        self,
        request: SearchRequest,
    ) -> tuple[list[Product], dict[str, str | None]]:
        result = await _parser.search(request.query)
        products: list[Product] = []
        for item in result.products:
            if not item.title or item.price is None or not item.product_url:
                continue
            products.append(self._to_product(item))
        return products, self._build_meta(result)

    async def search(self, request: SearchRequest) -> list[Product]:
        products, _ = await self.search_with_meta(request)
        return products


scraper = OzonScraper()
