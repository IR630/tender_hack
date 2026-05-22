from app.core.models import Product, SearchRequest
from app.scrapers.base import BaseScraper


class OzonScraper(BaseScraper):
    source = "ozon"

    async def search(self, request: SearchRequest) -> list[Product]:
        _ = request
        return []


scraper = OzonScraper()
