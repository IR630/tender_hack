from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WBFetchLayer(StrEnum):
    PRIMARY = "primary"
    BROWSER = "browser"


@dataclass
class RhythmState:
    """Per-session request pacing (phase 4 will attach one per VirtualUser)."""

    last_request_at: float = 0.0


@dataclass
class WBSearchResponse:
    products: list[dict]
    status_code: int
    layer: WBFetchLayer = WBFetchLayer.PRIMARY
    pow_header: str | None = None
    error: str | None = None


@dataclass
class WBMetricsSnapshot:
    requests_total: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors_total: int = 0
    primary_requests: int = 0
    browser_requests: int = 0


@dataclass
class WBMetrics:
    requests_total: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors_total: int = 0
    primary_requests: int = 0
    browser_requests: int = 0

    def record_request(self, *, layer: WBFetchLayer, cache_hit: bool = False) -> None:
        self.requests_total += 1
        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
        if layer == WBFetchLayer.PRIMARY:
            self.primary_requests += 1
        elif layer == WBFetchLayer.BROWSER:
            self.browser_requests += 1

    def record_error(self) -> None:
        self.errors_total += 1

    def snapshot(self) -> WBMetricsSnapshot:
        return WBMetricsSnapshot(
            requests_total=self.requests_total,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
            errors_total=self.errors_total,
            primary_requests=self.primary_requests,
            browser_requests=self.browser_requests,
        )
