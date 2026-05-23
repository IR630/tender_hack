from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["wildberries", "ozon", "yandex_market", "other"]


class Product(BaseModel):
    source: SourceType
    source_domain: str
    title: str
    description: str = ""
    price: int
    currency: str = "RUB"
    image_url: str
    product_url: str
    characteristics: dict[str, str] = Field(default_factory=dict)
    rating: float | None = None
    reviews_count: int | None = None
    relevance_score: float = 0.0
    confidence: float = 1.0


class SearchQuery(BaseModel):
    original: str
    corrected: str
    region: str
    region_name: str
    synonyms_used: list[str] = Field(default_factory=list)
    took_ms: int = 0


class SearchSummary(BaseModel):
    total_found: int = 0
    min_price: int | None = None
    median_price: int | None = None
    max_price: int | None = None


class SearchGroup(BaseModel):
    source: SourceType
    display_name: str
    count: int = 0
    min_price: int | None = None
    domains: list[str] = Field(default_factory=list)
    products: list[Product] = Field(default_factory=list)
    error: str | None = None
    status: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    region: str = "moscow"


class SearchResponse(BaseModel):
    query: SearchQuery
    summary: SearchSummary
    groups: list[SearchGroup]


class SearchTaskCreateResponse(BaseModel):
    task_id: str


class SearchTaskStatusResponse(BaseModel):
    task_id: str
    status: Literal["pending", "running", "completed", "failed"]
    message: str | None = None
    error: str | None = None
    result: SearchResponse | None = None
    groups: list[SearchGroup] = Field(default_factory=list)
