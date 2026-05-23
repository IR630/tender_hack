from __future__ import annotations

from pydantic import BaseModel, Field


class UrlCandidate(BaseModel):
    url: str
    domain: str
    title: str = ""
    snippet: str = ""
    source: str = "searxng"
    category: str | None = None
    similarity: float = 0.0
    cached_price_rub: int | None = None
    cached_image_url: str = ""
    cached_description: str = ""


class OtherExtractResult(BaseModel):
    title: str
    description: str = ""
    price_rub: int
    image_url: str
    product_url: str
    source_domain: str
    characteristics: dict[str, str] = Field(default_factory=dict)
    confidence: float = 0.8
    extraction_method: str = "json_ld"
    relevance_score: float = 0.0


class MeiliProductDoc(BaseModel):
    id: str
    url: str
    domain: str
    title: str
    category: str = "unknown"
    image_url: str = ""
    last_price: int = 0
    keywords: list[str] = Field(default_factory=list)
    confidence: float = 1.0
