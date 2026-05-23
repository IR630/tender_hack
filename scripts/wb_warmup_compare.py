#!/usr/bin/env python3
"""Compare WB search success rate with and without cookie warmup (phase 1)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.models import SearchRequest  # noqa: E402
from app.scrapers.wb.circuit import reset_circuit_for_tests  # noqa: E402
from app.scrapers.wb import reset_session_for_tests, scraper, wb_metrics  # noqa: E402

QUERIES = [
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


async def _run_batch(*, warmup: bool, total: int, interval_sec: float, max_retries: int) -> dict:
    settings.wb_warmup_enabled = warmup
    settings.wb_search_max_retries = max_retries
    await reset_session_for_tests()

    successes = 0
    failures = 0
    started = time.perf_counter()

    for i in range(total):
        query = QUERIES[i % len(QUERIES)]
        products = await scraper.search(SearchRequest(query=query, region="moscow"))
        if products and scraper.last_error is None:
            successes += 1
        else:
            failures += 1
        reset_circuit_for_tests()
        if interval_sec > 0 and i + 1 < total:
            await asyncio.sleep(interval_sec)

    elapsed = time.perf_counter() - started
    success_rate = successes / total if total else 0.0
    return {
        "warmup_enabled": warmup,
        "total": total,
        "successes": successes,
        "failures": failures,
        "success_rate": round(success_rate, 4),
        "elapsed_sec": round(elapsed, 2),
        "metrics": wb_metrics.snapshot(),
    }


async def main_async(
    *,
    total: int,
    interval_sec: float,
    output: Path,
    max_retries: int,
    gate_without_lt: float,
    gate_with_ge: float,
) -> None:
    print(f"=== WB warmup comparison ({total} requests, {interval_sec}s interval) ===")

    print("\n--- WITHOUT warmup ---")
    without = await _run_batch(
        warmup=False, total=total, interval_sec=interval_sec, max_retries=max_retries
    )
    print(json.dumps(without, ensure_ascii=False, indent=2))

    print("\n--- WITH warmup ---")
    with_warmup = await _run_batch(
        warmup=True, total=total, interval_sec=interval_sec, max_retries=max_retries
    )
    print(json.dumps(with_warmup, ensure_ascii=False, indent=2))

    report = {
        "without_warmup": without,
        "with_warmup": with_warmup,
        "pass": with_warmup["success_rate"] >= gate_with_ge and without["success_rate"] < gate_without_lt,
        "gate": {"without_lt": gate_without_lt, "with_ge": gate_with_ge},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {output}")
    print(f"Phase 1 gate: {'PASS' if report['pass'] else 'FAIL'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="WB warmup before/after comparison")
    parser.add_argument("--total", type=int, default=50)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--max-retries", type=int, default=None, help="Override WB_SEARCH_MAX_RETRIES")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Fast smoke: 12 requests, 1s interval, no retries (~30s per batch)",
    )
    parser.add_argument(
        "--acceptance",
        action="store_true",
        help="Full phase-1 gate: 50 requests, 5s interval (default thresholds)",
    )
    parser.add_argument("--output", type=Path, default=REPORTS_DIR / "warmup_compare.json")
    args = parser.parse_args()

    total = args.total
    interval = args.interval
    max_retries = args.max_retries
    gate_without_lt = 0.70
    gate_with_ge = 0.95

    if args.quick:
        total = 12
        interval = 1.0
        max_retries = 0 if max_retries is None else max_retries
        gate_with_ge = 0.75
        gate_without_lt = 0.85
    elif args.acceptance:
        total = 50
        interval = 5.0
        max_retries = 1 if max_retries is None else max_retries
    elif max_retries is None:
        max_retries = settings.wb_search_max_retries

    asyncio.run(
        main_async(
            total=total,
            interval_sec=interval,
            output=args.output,
            max_retries=max_retries,
            gate_without_lt=gate_without_lt,
            gate_with_ge=gate_with_ge,
        )
    )


if __name__ == "__main__":
    main()
