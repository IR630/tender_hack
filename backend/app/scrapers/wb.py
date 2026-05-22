from app.core.models import Product, SearchRequest
from app.scrapers.base import BaseScraper


class WildberriesScraper(BaseScraper):
    source = "wildberries"

    async def search(self, request: SearchRequest) -> list[Product]:
        _ = request
        return []


scraper = WildberriesScraper()
