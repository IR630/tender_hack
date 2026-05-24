from __future__ import annotations

import logging
from urllib.parse import urlparse

from other_public_scraper.url_heuristics import url_quality_score

logger = logging.getLogger(__name__)

_MODEL = None
_MODEL_DISABLED = False


def _get_model():
    global _MODEL, _MODEL_DISABLED
    if _MODEL_DISABLED:
        return None
    if _MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer

            _MODEL = SentenceTransformer("cointegrated/rubert-tiny2")
        except Exception as exc:
            logger.warning("relevance model unavailable, using token overlap: %s", exc)
            _MODEL_DISABLED = True
            return None
    return _MODEL


def _token_overlap_score(query: str, text: str) -> float:
    tokens = [token for token in query.lower().split() if len(token) > 2]
    if not tokens:
        return 0.0
    haystack = text.lower()
    hits = 0
    for token in tokens:
        if token in haystack:
            hits += 1
            continue
        stem = token[: max(3, len(token) - 1)]
        if len(stem) >= 4 and stem in haystack:
            hits += 1
    return hits / len(tokens)


def cosine_similarity_batch(query: str, text: str) -> float:
    if not query.strip() or not text.strip():
        return 0.0
    try:
        model = _get_model()
        if model is None:
            return _token_overlap_score(query, text)
        embeddings = model.encode([query, text], normalize_embeddings=True)
        return float(embeddings[1] @ embeddings[0])
    except Exception as exc:
        logger.warning("relevance similarity failed: %s", exc)
        return _token_overlap_score(query, text)


def _listing_depth_bonus(url: str) -> float:
    """Prefer deeper catalog paths (e.g. /catalog/tyres/leto/) over shallow listings."""
    segments = [part for part in urlparse(url).path.split("/") if part]
    if len(segments) >= 3:
        return 0.12
    if len(segments) <= 1:
        return -0.08
    return 0.0


def _diversify_by_domain(scored: list, *, limit: int, max_per_domain: int = 2) -> list:
    picked: list = []
    domain_counts: dict[str, int] = {}
    for candidate in scored:
        domain = (candidate.domain or "").lower().replace("www.", "")
        if not domain:
            domain = candidate.url.split("/")[2] if "://" in candidate.url else "unknown"
        if domain_counts.get(domain, 0) >= max_per_domain:
            continue
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        picked.append(candidate)
        if len(picked) >= limit:
            break
    if len(picked) < limit:
        seen = {c.url for c in picked}
        for candidate in scored:
            if candidate in picked or candidate.url in seen:
                continue
            picked.append(candidate)
            seen.add(candidate.url)
            if len(picked) >= limit:
                break
    return picked


def rank_candidates(query: str, candidates: list, *, threshold: float, limit: int):
    if not candidates:
        return []
    scored = []
    rejected: list[tuple[str, float]] = []
    for candidate in candidates:
        text = f"{candidate.title} {candidate.snippet}".strip()
        sim = cosine_similarity_batch(query, text)
        quality = url_quality_score(candidate.url)
        combined = sim + max(quality, 0) * 0.15 + _listing_depth_bonus(candidate.url)
        if sim >= threshold:
            candidate.similarity = combined
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
    return _diversify_by_domain(scored, limit=limit)
