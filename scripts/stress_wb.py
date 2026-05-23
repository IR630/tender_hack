#!/usr/bin/env python3
"""Stress-test Wildberries parser and emit phase report JSON."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.models import SearchRequest  # noqa: E402
from app.scrapers.wb import reset_session_for_tests, scraper, wb_metrics  # noqa: E402


DEFAULT_QUERIES = [
    "ноутбук",
    "iphone 15",
    "наушники",
    "кроссовки",
    "принтер",
    "монитор",
    "ssd 1tb",
    "чехол samsung",
    "кофемашина",
    "шины 205 55 r16",
]


async def _run_stress(
    *,
    total: int,
    concurrency: int,
    interval_sec: float,
    warmup: bool,
    unique_queries: int,
) -> dict:
    os.environ["WB_WARMUP_ENABLED"] = "true" if warmup else "false"
    settings.wb_warmup_enabled = warmup

    await reset_session_for_tests()
    queries = [DEFAULT_QUERIES[i % len(DEFAULT_QUERIES)] for i in range(unique_queries)]
    workload = [queries[i % len(queries)] for i in range(total)]

    sem = asyncio.Semaphore(concurrency)
    started = time.perf_counter()

    async def one(query: str) -> bool:
        async with sem:
            products = await scraper.search(SearchRequest(query=query, region="moscow"))
            ok = bool(products) and scraper.last_error is None
            if interval_sec > 0:
                await asyncio.sleep(interval_sec)
            return ok

    outcomes = await asyncio.gather(*(one(q) for q in workload))
    elapsed = time.perf_counter() - started
    scraper_successes = sum(1 for ok in outcomes if ok)
    report = wb_metrics.snapshot()
    report["scraper"] = {
        "successes": scraper_successes,
        "failures": total - scraper_successes,
        "success_rate": round(scraper_successes / total, 4) if total else 0.0,
    }
    report["stress"] = {
        "total": total,
        "concurrency": concurrency,
        "interval_sec": interval_sec,
        "warmup_enabled": warmup,
        "unique_queries": unique_queries,
        "elapsed_sec": round(elapsed, 2),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Wildberries stress runner")
    parser.add_argument("--total", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--interval", type=float, default=0.0)
    parser.add_argument("--no-warmup", action="store_true", help="Disable cookie warmup")
    parser.add_argument("--unique", type=int, default=10)
    parser.add_argument("--output", type=Path, default=REPORTS_DIR / "phase_1.json")
    args = parser.parse_args()

    report = asyncio.run(
        _run_stress(
            total=args.total,
            concurrency=args.concurrency,
            interval_sec=args.interval,
            warmup=not args.no_warmup,
            unique_queries=args.unique,
        )
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== WB stress report ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
