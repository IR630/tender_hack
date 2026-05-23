from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Response

from app.utils.image_urls import is_allowed_image_host, normalize_marketplace_image_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/proxy")
async def proxy_image(url: str, domain: str = "") -> Response:
    normalized = normalize_marketplace_image_url(url)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="invalid image url")
    if not is_allowed_image_host(normalized, source_domain=domain):
        raise HTTPException(status_code=403, detail="image host not allowed")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            upstream = await client.get(
                normalized,
                headers={
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    ),
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("image_proxy_fetch_failed url=%s error=%s", normalized[:120], exc)
        raise HTTPException(status_code=502, detail="failed to fetch image") from exc

    if upstream.status_code != 200:
        logger.warning(
            "image_proxy_upstream_status url=%s status=%s",
            normalized[:120],
            upstream.status_code,
        )
        raise HTTPException(status_code=upstream.status_code, detail="upstream image error")

    content_type = upstream.headers.get("content-type", "image/jpeg")
    return Response(
        content=upstream.content,
        media_type=content_type.split(";")[0],
        headers={"Cache-Control": "public, max-age=86400"},
    )
