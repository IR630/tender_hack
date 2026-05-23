from __future__ import annotations

import re

logger = None  # lazy


def parse_price(raw: str | None) -> int | None:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d]", "", raw.replace("\u202f", "").replace(" ", ""))
    if not cleaned:
        return None
    try:
        value = int(cleaned)
        return value if value > 0 else None
    except ValueError:
        return None
