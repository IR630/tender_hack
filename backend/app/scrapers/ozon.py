from __future__ import annotations

from app.core.config import settings
from app.core.models import Product, SearchRequest
from app.core.regions import resolve_region
from app.scrapers import ozon_browser
from app.scrapers.base import BaseScraper
from ozon_public_scraper import OzonPublicScraper, ScraperError


class OzonScraper(BaseScraper):
    source = "ozon"

    def __init__(self) -> None:
        self._public = OzonPublicScraper()

    async def search(self, request: SearchRequest) -> list[Product]:
        if settings.ozon_use_browser:
            return await self._search_browser(request)
        return await self._search_public(request)

    async def _search_browser(self, request: SearchRequest) -> list[Product]:
        self.clear_error()
        raw, error, status = await ozon_browser.search_products(request.query.strip())
        if status == ozon_browser.OZON_WAF_STATUS:
            self.set_source_status(status)
            self.set_error(error or ozon_browser.OZON_WAF_MESSAGE)
            return []
        if error:
            self.set_error(error)
            return []
        return [
            Product(
                source="ozon",
                source_domain="ozon.ru",
                title=str(item["title"]),
                price=int(item["price"] or 0),
                image_url=str(item.get("image") or "https://www.ozon.ru/favicon.ico"),
                product_url=str(item["url"]),
                characteristics=dict(item.get("characteristics") or {}),
                description=str(item.get("description") or ""),
            )
            for item in raw
        ]

    async def _search_public(self, request: SearchRequest) -> list[Product]:
        region = resolve_region(request.region)
        self.clear_error()
        try:
            results = await self._public.search(request.query, region=region.id, limit=30)
        except ScraperError as exc:
            self.set_error(f"{exc.error_type.value}: {exc.message}")
            return []

        products: list[Product] = []
        for item in results:
            chars = dict(item.characteristics)
            if item.incomplete:
                chars["price_unavailable"] = "true"
            products.append(
                Product(
                    source="ozon",
                    source_domain="ozon.ru",
                    title=item.title,
                    price=item.price_rub or 0,
                    image_url=str(item.image_url or "https://www.ozon.ru/favicon.ico"),
                    product_url=str(item.product_url),
                    characteristics=chars,
                    description=item.description or "",
                )
            )
        return products


scraper = OzonScraper()
