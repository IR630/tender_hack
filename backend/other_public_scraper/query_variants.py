"""Generate alternate search queries for ambiguous product names."""

from __future__ import annotations

import re

_IPHONE_SE_RE = re.compile(r"^iphone\s+\d+\s+se\b", re.IGNORECASE)
_CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
_IPHONE_CYR_RE = re.compile(r"айфон|айфон", re.IGNORECASE)
_OPTICS_QUERY_RE = re.compile(r"очк", re.IGNORECASE)


def _latin_iphone_variant(query: str) -> str | None:
    lower = query.lower()
    if not _CYRILLIC_RE.search(query) or "айфон" not in lower:
        return None
    latin = query
    for cyr, lat in (
        ("айфон", "iphone"),
        ("Айфон", "iPhone"),
        ("АЙФОН", "IPHONE"),
    ):
        latin = latin.replace(cyr, lat)
    return latin.strip() if latin.lower() != query.lower() else None


def search_query_variants(query: str) -> list[str]:
    """Return unique query variants, most specific first."""
    original = query.strip()
    if not original:
        return []

    variants: list[str] = [original]
    seen = {original.lower()}

    def _add(value: str) -> None:
        cleaned = value.strip()
        if cleaned and cleaned.lower() not in seen:
            variants.append(cleaned)
            seen.add(cleaned.lower())

    lower = original.lower()

    if _IPHONE_SE_RE.match(lower):
        simplified = re.sub(r"(iphone)\s+\d+\s+(se\b.*)", r"\1 \2", original, flags=re.IGNORECASE)
        _add(simplified)

    latin = _latin_iphone_variant(original)
    if latin:
        _add(latin)
        if "apple" not in lower and "apple" not in latin.lower():
            _add(f"Apple {latin}")

    if _IPHONE_CYR_RE.search(original) or (
        re.search(r"iphone\s+\d{1,2}\b", lower) and " se" not in lower
    ):
        _add(f"{original} купить")
        if latin:
            _add(f"{latin} купить")

    if _OPTICS_QUERY_RE.search(original):
        _add(f"{original} купить")
        _add("оправы для очков")

    return variants
