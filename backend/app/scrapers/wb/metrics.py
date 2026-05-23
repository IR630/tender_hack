from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(int(len(ordered) * pct / 100), len(ordered) - 1)
    return round(ordered[index], 2)


@dataclass
class WBMetricsCollector:
    """In-process WB metrics for GET /metrics/wb and stress reports."""

    total_requests: int = 0
    successful_requests: int = 0
    cache_hits: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    status_codes: Counter[int] = field(default_factory=Counter)
    fallback_levels: Counter[str] = field(default_factory=Counter)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def record(
        self,
        *,
        success: bool,
        latency_ms: float,
        status_code: int,
        cache_hit: bool = False,
        fallback_level: str = "PRIMARY",
    ) -> None:
        async with self._lock:
            self.total_requests += 1
            if success:
                self.successful_requests += 1
            if cache_hit:
                self.cache_hits += 1
            self.latencies_ms.append(latency_ms)
            self.status_codes[status_code] += 1
            self.fallback_levels[fallback_level] += 1

    def snapshot(self) -> dict[str, Any]:
        total = self.total_requests
        success_rate = round(self.successful_requests / total, 4) if total else 0.0
        cache_hit_rate = round(self.cache_hits / total, 4) if total else 0.0
        return {
            "total_requests": total,
            "successful_requests": self.successful_requests,
            "success_rate": success_rate,
            "cache_hit_rate": cache_hit_rate,
            "latency_ms": {
                "p50": _percentile(self.latencies_ms, 50),
                "p95": _percentile(self.latencies_ms, 95),
            },
            "status_codes": dict(sorted(self.status_codes.items())),
            "fallback_level_distribution": dict(self.fallback_levels),
            "generated_at": time.time(),
        }

    async def reset(self) -> None:
        async with self._lock:
            self.total_requests = 0
            self.successful_requests = 0
            self.cache_hits = 0
            self.latencies_ms.clear()
            self.status_codes.clear()
            self.fallback_levels.clear()


wb_metrics = WBMetricsCollector()
