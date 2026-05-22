from dataclasses import dataclass


@dataclass
class ProcessedQuery:
    original: str
    corrected: str
    synonyms: list[str]


def process_query(query: str) -> ProcessedQuery:
    normalized = query.strip()
    return ProcessedQuery(original=normalized, corrected=normalized, synonyms=[])
