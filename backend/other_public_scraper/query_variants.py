"""Generate alternate search queries for ambiguous product names."""

from __future__ import annotations

import re

_IPHONE_SE_RE = re.compile(r"^iphone\s+\d+\s+se\b", re.IGNORECASE)


def search_query_variants(query: str) -> list[str]:
    """Return unique query variants, most specific first."""
    original = query.strip()
    if not original:
        return []

    variants: list[str] = [original]
    lower = original.lower()

    if _IPHONE_SE_RE.match(lower):
        simplified = re.sub(r"(iphone)\s+\d+\s+(se\b.*)", r"\1 \2", original, flags=re.IGNORECASE)
        if simplified.lower() not in {v.lower() for v in variants}:
            variants.append(simplified.strip())

    return variants
