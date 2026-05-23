from dataclasses import dataclass

from app.query.yandex_spell import fetch_yandex_spell_correction

# Short marketplace queries that WB/YM often treat as empty unless expanded.
_LOCAL_QUERY_EXPANSIONS: dict[str, str] = {
    "комп": "компьютер",
    "ноут": "ноутбук",
    "тел": "телефон",
    "айф": "айфон",
    # Common Cyrillic misspellings of «айфон» / iPhone.
    "ипхон": "айфон",
    "ипон": "айфон",
    "айфн": "айфон",
    "афон": "айфон",
}


@dataclass
class ProcessedQuery:
    original: str
    corrected: str
    synonyms: list[str]


async def process_query(query: str) -> ProcessedQuery:
    original = query.strip()
    if not original:
        return ProcessedQuery(original="", corrected="", synonyms=[])

    lowered = original.lower()
    local = _LOCAL_QUERY_EXPANSIONS.get(lowered)
    if local:
        return ProcessedQuery(original=original, corrected=local, synonyms=[])

    corrected = await fetch_yandex_spell_correction(original) or original
    return ProcessedQuery(original=original, corrected=corrected, synonyms=[])
