from app.core.models import Product, SearchRequest
from app.scrapers.base import BaseScraper


class YandexMarketScraper(BaseScraper):
    source = "yandex_market"

    async def search(self, request: SearchRequest) -> list[Product]:
        _ = request
        return []


scraper = YandexMarketScraper()
