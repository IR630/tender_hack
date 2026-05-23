from dataclasses import dataclass

from app.query.yandex_spell import fetch_yandex_spell_correction


@dataclass
class ProcessedQuery:
    original: str
    corrected: str
    synonyms: list[str]


async def process_query(query: str) -> ProcessedQuery:
    original = query.strip()
    if not original:
        return ProcessedQuery(original="", corrected="", synonyms=[])

    corrected = await fetch_yandex_spell_correction(original) or original
    return ProcessedQuery(original=original, corrected=corrected, synonyms=[])
