from __future__ import annotations

import re

logger = None  # lazy


def parse_price(raw: str | None) -> int | None:
    if not raw:
        return None
    stripped = raw.strip().replace("\u202f", "").replace(" ", "")
    decimal_match = re.match(r"^(\d+)[.,](\d{1,2})$", stripped)
    if decimal_match:
        value = int(decimal_match.group(1))
        return value if value > 0 else None
    cleaned = re.sub(r"[^\d]", "", stripped)
    if not cleaned:
        return None
    try:
        value = int(cleaned)
        return value if value > 0 else None
    except ValueError:
        return None
