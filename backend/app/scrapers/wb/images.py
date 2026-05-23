from __future__ import annotations

import asyncio
import logging

from curl_cffi.requests import AsyncSession

from app.core.models import Product
from app.scrapers.wb.assemble import host_for_nm, image_url
from app.scrapers.wb.config import BASKET_MAX, BASKET_MIN

logger = logging.getLogger(__name__)

_PROBE_DEPTH = 8


def candidate_hosts(nm: int) -> list[int]:
    hint = host_for_nm(nm)
    upper = min(BASKET_MAX, hint + _PROBE_DEPTH)
    return list(range(max(BASKET_MIN, hint), upper + 1))


async def _probe_host(session: AsyncSession, nm: int, host: int) -> int | None:
    url = image_url(host, nm)
    try:
        response = await session.head(url, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return host
    except Exception:
        return None
    return None


async def resolve_image_host(session: AsyncSession, nm: int) -> int:
    hint = host_for_nm(nm)
    hosts = candidate_hosts(nm)
    tasks = [_probe_host(session, nm, host) for host in hosts]
    for task in asyncio.as_completed(tasks):
        resolved = await task
        if resolved is not None:
            if resolved != hint:
                logger.debug("WB image host corrected nm=%s hint=%s resolved=%s", nm, hint, resolved)
            return resolved
    return hint


async def resolve_product_images(products: list[Product]) -> list[Product]:
    if not products:
        return products

    async with AsyncSession(impersonate="chrome131") as session:
        hosts = await asyncio.gather(
            *[resolve_image_host(session, _nm_from_product(product)) for product in products]
        )

    resolved: list[Product] = []
    for product, host in zip(products, hosts, strict=True):
        nm = _nm_from_product(product)
        resolved.append(product.model_copy(update={"image_url": image_url(host, nm)}))
    return resolved


def _nm_from_product(product: Product) -> int:
    tail = product.product_url.rstrip("/").split("/")[-2]
    return int(tail)
