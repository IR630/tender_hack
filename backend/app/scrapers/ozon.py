from app.core.models import Product, SearchRequest
from app.core.regions import resolve_region
from app.scrapers.base import BaseScraper


class OzonScraper(BaseScraper):
    source = "ozon"

    async def search(self, request: SearchRequest) -> list[Product]:
        _ = resolve_region(request.region)
        return []


scraper = OzonScraper()
