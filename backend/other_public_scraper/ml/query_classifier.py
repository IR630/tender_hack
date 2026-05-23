from __future__ import annotations

from other_public_scraper.config import CATEGORY_PROTOTYPES
from other_public_scraper.ml.relevance_filter import cosine_similarity_batch


def classify_query(query: str) -> str:
    if not query.strip():
        return "unknown"
    scores = {
        category: cosine_similarity_batch(query, prototype)
        for category, prototype in CATEGORY_PROTOTYPES.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] >= 0.35 else "unknown"
