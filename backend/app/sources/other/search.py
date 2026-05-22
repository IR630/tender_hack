from app.core.models import Product, SearchRequest
from app.core.regions import resolve_region


async def search_other_sources(request: SearchRequest) -> list[Product]:
    _ = resolve_region(request.region)
    return []
