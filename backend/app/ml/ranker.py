from app.core.models import Product


def rank_products(query: str, products: list[Product]) -> list[Product]:
    _ = query
    return sorted(products, key=lambda product: product.relevance_score, reverse=True)
