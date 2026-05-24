from __future__ import annotations

from app.core.config import settings
from app.core.models import Product, SearchRequest
from app.core.regions import resolve_region
from app.scrapers import ozon_browser
from app.scrapers.base import BaseScraper
from ozon_public_scraper import OzonPublicScraper, ScraperError


class OzonScraper(BaseScraper):
    source = "ozon"
    FULL_LIMIT = 15

    def __init__(self) -> None:
        self._public = OzonPublicScraper()

    async def search(self, request: SearchRequest, *, on_partial=None) -> list[Product]:
        if settings.ozon_use_browser:
            return await self._search_browser(request, on_partial=on_partial)
        return await self._search_public(request, on_partial=on_partial)

    async def _search_browser(self, request: SearchRequest, *, on_partial=None) -> list[Product]:
        self.clear_error()
        partial_sent = False

        def _to_product(item) -> Product:
            return Product(
                source="ozon",
                source_domain="ozon.ru",
                title=str(item["title"]),
                price=int(item["price"] or 0),
                image_url=str(item.get("image") or "https://www.ozon.ru/favicon.ico"),
                product_url=str(item["url"]),
                characteristics=dict(item.get("characteristics") or {}),
                description=str(item.get("description") or ""),
                rating=float(item["rating"]) if item.get("rating") is not None else None,
                reviews_count=(
                    int(item["reviews_count"])
                    if item.get("reviews_count") is not None
                    else None
                ),
            )

        async def _on_partial_raw(raw_items) -> None:
            nonlocal partial_sent
            if partial_sent or not on_partial or not raw_items:
                return
            partial_sent = True
            try:
                await on_partial([_to_product(item) for item in raw_items[: self.FAST_LIMIT]])
            except Exception:
                pass

        raw, error, status = await ozon_browser.search_products(
            request.query.strip(),
            region=request.region,
            on_partial_raw=_on_partial_raw if on_partial else None,
        )
        if status == ozon_browser.OZON_WAF_STATUS:
            self.set_source_status(status)
            self.set_error(error or ozon_browser.OZON_WAF_MESSAGE)
            return []
        if error:
            self.set_error(error)
            return []
        products = [_to_product(item) for item in raw]
        if on_partial and products and not partial_sent:
            try:
                await on_partial(products[: self.FAST_LIMIT])
            except Exception:
                pass
        return products[: self.FULL_LIMIT]

    async def _search_public(self, request: SearchRequest, *, on_partial=None) -> list[Product]:
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
        if on_partial and products:
            try:
                await on_partial(products[: self.FAST_LIMIT])
            except Exception:
                pass
        return products[: self.FULL_LIMIT]


scraper = OzonScraper()






