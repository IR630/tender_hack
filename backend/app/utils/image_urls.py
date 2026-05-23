from __future__ import annotations

import re
from urllib.parse import urlparse

_YANDEX_MPIC_RE = re.compile(
    r"(https://avatars\.mds\.yandex\.net/get-mpic/\d+/[^/]+)/[^/]+$",
    re.IGNORECASE,
)

ALLOWED_IMAGE_HOST_SUFFIXES = (
    "avatars.mds.yandex.net",
    "ir.ozone.ru",
    "ozone.ru",
    "wbbasket.ru",
    "wb.ru",
    "cmstore.ru",
    "re-store.ru",
    "mikrovuho.ru",
    "domicro.ru",
    "microgadgets.ru",
    "mikron45.ru",
)


def normalize_marketplace_image_url(url: str | None) -> str:
    """Prefer full-size Yandex Market images instead of broken thumbnail suffixes."""
    if not url:
        return ""
    cleaned = url.strip()
    match = _YANDEX_MPIC_RE.match(cleaned)
    if match:
        return f"{match.group(1)}/orig"
    return cleaned


def is_allowed_image_host(url: str, *, source_domain: str = "") -> bool:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    normalized_domain = source_domain.lower().removeprefix("www.")
    if normalized_domain and (host == normalized_domain or host.endswith(f".{normalized_domain}")):
        return True
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in ALLOWED_IMAGE_HOST_SUFFIXES)
