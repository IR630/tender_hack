from __future__ import annotations

from other_public_scraper.config import CATEGORY_PROTOTYPES
from other_public_scraper.ml.relevance_filter import cosine_similarity_batch

_TIRE_QUERY_HINTS = ("шин", "резин", "tyre", "tire", "колес")
_ORGTECH_QUERY_HINTS = (
    "ноутбук",
    "принтер",
    "монитор",
    "айфон",
    "iphone",
    "компьютер",
    "ипхон",
    "ипон",
    "мыш",
    "клавиат",
    "джойстик",
)


def classify_query(query: str) -> str:
    if not query.strip():
        return "unknown"
    query_lower = query.lower()
    if any(hint in query_lower for hint in _TIRE_QUERY_HINTS):
        return "tires"
    if any(hint in query_lower for hint in _ORGTECH_QUERY_HINTS):
        return "orgtech"
    scores = {
        category: cosine_similarity_batch(query, prototype)
        for category, prototype in CATEGORY_PROTOTYPES.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] >= 0.35 else "unknown"
