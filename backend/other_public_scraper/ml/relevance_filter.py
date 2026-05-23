from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer("cointegrated/rubert-tiny2")
    return _MODEL


def _token_overlap_score(query: str, text: str) -> float:
    tokens = [token for token in query.lower().split() if len(token) > 2]
    if not tokens:
        return 0.0
    haystack = text.lower()
    hits = sum(1 for token in tokens if token in haystack)
    return hits / len(tokens)


def cosine_similarity_batch(query: str, text: str) -> float:
    if not query.strip() or not text.strip():
        return 0.0
    try:
        model = _get_model()
        embeddings = model.encode([query, text], normalize_embeddings=True)
        return float(embeddings[1] @ embeddings[0])
    except Exception as exc:
        logger.warning("relevance similarity failed: %s", exc)
        return _token_overlap_score(query, text)


def rank_candidates(query: str, candidates: list, *, threshold: float, limit: int):
    if not candidates:
        return []
    scored = []
    rejected: list[tuple[str, float]] = []
    for candidate in candidates:
        text = f"{candidate.title} {candidate.snippet}".strip()
        sim = cosine_similarity_batch(query, text)
        if sim >= threshold:
            candidate.similarity = sim
            scored.append(candidate)
        else:
            rejected.append((candidate.url[:80], sim))
    scored.sort(key=lambda item: item.similarity, reverse=True)
    if rejected:
        logger.info(
            "other_rank_rejected query=%r threshold=%.2f rejected=%d sample=%s",
            query,
            threshold,
            len(rejected),
            rejected[:3],
        )
    logger.info(
        "other_rank query=%r candidates=%d passed=%d limit=%d",
        query,
        len(candidates),
        len(scored),
        limit,
    )
    return scored[:limit]
