from app.core.models import Product, SearchRequest


async def search_other_sources(request: SearchRequest) -> list[Product]:
    _ = request
    return []
