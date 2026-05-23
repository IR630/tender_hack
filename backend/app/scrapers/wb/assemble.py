from __future__ import annotations

from app.core.models import Product
from app.scrapers.wb.config import (
    BASKET_HOST_FMT,
    BASKET_MAX,
    BASKET_MIN,
    HOST_HINT_RANGES,
    PRODUCT_URL_FMT,
)


def price_kopecks(product: dict) -> int:
    sizes = product.get("sizes") or []
    if sizes:
        price = (sizes[0] or {}).get("price") or {}
        kopecks = price.get("product") or price.get("total") or price.get("basic")
        if kopecks:
            return int(kopecks)
    legacy = product.get("salePriceU") or product.get("priceU")
    return int(legacy) if legacy else 0


def host_hint(vol: int) -> int:
    for max_vol, host in HOST_HINT_RANGES:
        if vol <= max_vol:
            return host
    return HOST_HINT_RANGES[-1][1] + 1


def host_for_nm(nm: int) -> int:
    vol = nm // 100000
    return max(BASKET_MIN, min(host_hint(vol), BASKET_MAX))


def image_url(host: int, nm: int) -> str:
    vol, part = nm // 100000, nm // 1000
    return f"{BASKET_HOST_FMT.format(host=host)}/vol{vol}/part{part}/{nm}/images/big/1.webp"


def base_characteristics(product: dict) -> dict[str, str]:
    chars: dict[str, str] = {}
    if product.get("brand"):
        chars["Бренд"] = str(product["brand"])
    if product.get("supplier"):
        chars["Продавец"] = str(product["supplier"])
    return chars


def extended_characteristics(product: dict) -> dict[str, str]:
    chars = base_characteristics(product)
    entity = product.get("entity")
    if entity:
        chars["Категория"] = str(entity)

    colors = product.get("colors")
    if isinstance(colors, list):
        color_names = [str(item).strip() for item in colors if str(item).strip()]
        if color_names:
            chars["Цвет"] = ", ".join(color_names)

    supplier_rating = product.get("supplierRating")
    if supplier_rating is not None:
        chars["Рейтинг продавца"] = str(supplier_rating)

    total_quantity = product.get("totalQuantity")
    if total_quantity is not None:
        chars["В наличии"] = str(total_quantity)

    return chars


def build_description(
    *,
    characteristics: dict[str, str],
    rating: float | None,
    reviews_count: int | None,
) -> str:
    lines: list[str] = []
    if characteristics:
        lines.append("Характеристики:")
        for label, value in characteristics.items():
            lines.append(f"• {label}: {value}")

    details: list[str] = []
    if rating is not None:
        rating_line = f"Рейтинг: {rating:g}"
        if reviews_count is not None:
            rating_line += f" ({reviews_count} отзывов)"
        details.append(rating_line)
    elif reviews_count is not None:
        details.append(f"Отзывов: {reviews_count}")

    if details:
        if lines:
            lines.append("")
        lines.extend(details)

    return "\n".join(lines).strip()


def build_product(raw: dict, image: str, characteristics: dict[str, str]) -> Product | None:
    nm = raw.get("id")
    name = raw.get("name")
    price = price_kopecks(raw)
    if not nm or not name or price <= 0:
        return None

    feedbacks = raw.get("nmFeedbacks") or raw.get("feedbacks")
    rating = raw.get("reviewRating") or raw.get("nmReviewRating") or raw.get("rating")
    rating_value = float(rating) if rating else None
    reviews_value = int(feedbacks) if feedbacks else None
    return Product(
        source="wildberries",
        source_domain="wildberries.ru",
        title=str(name),
        description=build_description(
            characteristics=characteristics,
            rating=rating_value,
            reviews_count=reviews_value,
        ),
        price=price,
        image_url=image,
        product_url=PRODUCT_URL_FMT.format(nm=nm),
        characteristics=characteristics,
        rating=rating_value,
        reviews_count=reviews_value,
    )


def assemble_products(raw_products: list[dict]) -> list[Product]:
    products: list[Product] = []
    for raw in raw_products:
        nm = raw.get("id")
        if not nm or not raw.get("name") or price_kopecks(raw) <= 0:
            continue
        host = host_for_nm(int(nm))
        product = build_product(
            raw,
            image_url(host, int(nm)),
            extended_characteristics(raw),
        )
        if product is not None:
            products.append(product)
    return products
