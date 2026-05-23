"""Local semantic filtering for Ozon broad search results."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import structlog

logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger(component="ozon_ml_filter")

_MODEL = None
_MODEL_NAME = "cointegrated/rubert-tiny2"


def _get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        struct_logger.info("ozon_ml_model_loading", model=_MODEL_NAME)
        _MODEL = SentenceTransformer(_MODEL_NAME)
        struct_logger.info("ozon_ml_model_ready", model=_MODEL_NAME)
    return _MODEL


def filter_top_k_by_similarity(
    query: str,
    products: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Rank products by cosine similarity(query, title) and return top-k."""
    if not products:
        return []
    if len(products) <= top_k:
        return [dict(p) for p in products]

    try:
        model = _get_model()
        titles = [str(p.get("title") or "") for p in products]
        embeddings = model.encode([query, *titles], normalize_embeddings=True)
        query_vec = embeddings[0]
        title_vecs = embeddings[1:]
        similarities = title_vecs @ query_vec

        frame = pd.DataFrame(products).copy()
        frame["similarity"] = similarities
        frame = frame.sort_values("similarity", ascending=False).head(top_k)
        selected = frame.to_dict(orient="records")
        struct_logger.info(
            "ozon_ml_filter_applied",
            query=query,
            input_count=len(products),
            output_count=len(selected),
            top_score=float(selected[0]["similarity"]) if selected else 0.0,
        )
        return selected
    except Exception as exc:
        struct_logger.warning(
            "ozon_ml_filter_fallback",
            query=query,
            error=str(exc),
            fallback_count=top_k,
        )
        return [dict(p) for p in products[:top_k]]
