"""End-to-end smoke tests for the price aggregator.

Run:
    cd backend && uv run python -m scripts.smoke_search
    cd backend && uv run python -m scripts.smoke_search --quick   # skip Ozon
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.models import SearchRequest, SearchResponse
from app.orchestrator.search import run_search

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "smoke_latest.json"


@dataclass
class SmokeCase:
    id: int
    name: str
    query: str
    region: str = "moscow"
    min_sources_ok: int = 1
    min_total_products: int = 1
    require_sources: dict[str, int] = field(default_factory=dict)
    max_took_ms: int = 240_000
    allow_antibot_errors: bool = True


SMOKE_CASES: list[SmokeCase] = [
    SmokeCase(
        id=1,
        name="popular_phone",
        query="айфон 15",
        min_sources_ok=2,
        min_total_products=3,
    ),
    SmokeCase(
        id=2,
        name="ym_synonym_phone",
        query="телефон",
        min_sources_ok=1,
        min_total_products=5,
        require_sources={"yandex_market": 5},
    ),
    SmokeCase(
        id=3,
        name="other_tires",
        query="ШИНЫ",
        min_sources_ok=1,
        min_total_products=1,
        require_sources={"other": 1},
        max_took_ms=60_000,
    ),
    SmokeCase(
        id=4,
        name="other_optics",
        query="очки",
        min_sources_ok=1,
        min_total_products=1,
        require_sources={"other": 1},
        max_took_ms=60_000,
    ),
    SmokeCase(
        id=5,
        name="short_automotive",
        query="прив",
        min_sources_ok=1,
        min_total_products=1,
    ),
    SmokeCase(
        id=6,
        name="clothing",
        query="куртка",
        min_sources_ok=1,
        min_total_products=3,
    ),
    SmokeCase(
        id=7,
        name="headphones",
        query="наушники",
        min_sources_ok=1,
        min_total_products=30,
    ),
    SmokeCase(
        id=8,
        name="laptop",
        query="ноутбук",
        min_sources_ok=1,
        min_total_products=3,
    ),
    SmokeCase(
        id=9,
        name="query_variant_iphone_se",
        query="iphone 10 se",
        min_sources_ok=1,
        min_total_products=1,
    ),
    SmokeCase(
        id=10,
        name="product_field_quality",
        query="айфон 15",
        min_sources_ok=1,
        min_total_products=1,
    ),
]

ANTIBOT_MARKERS = ("429", "403", "капч", "captcha", "антибот", "smartcaptcha", "rate-limit")


def _is_antibot_error(error: str | None) -> bool:
    if not error:
        return False
    lowered = error.lower()
    return any(marker in lowered for marker in ANTIBOT_MARKERS)


def _validate_products(response: SearchResponse) -> list[str]:
    issues: list[str] = []
    for group in response.groups:
        for product in group.products:
            if not product.title.strip():
                issues.append(f"{group.source}: empty title")
            if product.price <= 0:
                issues.append(f"{group.source}: invalid price {product.price}")
            if not product.product_url.startswith("http"):
                issues.append(f"{group.source}: bad url {product.product_url[:40]}")
            if not product.image_url.startswith("http"):
                issues.append(f"{group.source}: bad image {product.image_url[:40]}")
    return issues


def _evaluate(case: SmokeCase, response: SearchResponse, took_ms: int) -> tuple[bool, list[str]]:
    notes: list[str] = []
    groups = {group.source: group for group in response.groups}

    ok_sources = 0
    total_products = 0
    for source, group in groups.items():
        total_products += group.count
        if group.count > 0:
            ok_sources += 1
            continue
        if group.error:
            if case.allow_antibot_errors and _is_antibot_error(group.error):
                notes.append(f"{source}: antibot ({group.error[:60]})")
            else:
                notes.append(f"{source}: {group.error[:80]}")

    passed = True
    if took_ms > case.max_took_ms:
        passed = False
        notes.append(f"timeout: {took_ms}ms > {case.max_took_ms}ms")

    if ok_sources < case.min_sources_ok:
        failed_sources = [
            source
            for source, group in groups.items()
            if group.count == 0 and not (case.allow_antibot_errors and _is_antibot_error(group.error))
        ]
        if total_products >= case.min_total_products and not failed_sources:
            notes.append(
                f"soft pass: {ok_sources} active sources, others antibot/unavailable"
            )
        else:
            passed = False
            notes.append(f"sources ok {ok_sources} < {case.min_sources_ok}")

    if total_products < case.min_total_products:
        passed = False
        notes.append(f"products {total_products} < {case.min_total_products}")

    for source, minimum in case.require_sources.items():
        count = groups.get(source, None)
        actual = count.count if count else 0
        if actual < minimum:
            passed = False
            notes.append(f"{source}: {actual} < {minimum}")

    if case.name == "product_field_quality":
        field_issues = _validate_products(response)
        if field_issues:
            passed = False
            notes.extend(field_issues[:5])
        else:
            notes.append("all product fields valid")

    if case.name == "query_variant_iphone_se":
        corrected = response.query.corrected.lower()
        if "iphone" not in corrected and "айфон" not in corrected:
            passed = False
            notes.append(f"unexpected correction: {response.query.corrected!r}")
        else:
            notes.append(f"corrected={response.query.corrected!r}")

    return passed, notes


async def _run_case(case: SmokeCase) -> dict:
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            run_search(SearchRequest(query=case.query, region=case.region)),
            timeout=case.max_took_ms / 1000,
        )
    except TimeoutError:
        took_ms = int((time.perf_counter() - started) * 1000)
        return {
            "id": case.id,
            "name": case.name,
            "query": case.query,
            "passed": False,
            "took_ms": took_ms,
            "notes": [f"asyncio timeout after {case.max_took_ms}ms"],
            "sources": {},
        }

    took_ms = int((time.perf_counter() - started) * 1000)
    passed, notes = _evaluate(case, response, took_ms)
    sources = {
        group.source: {
            "count": group.count,
            "error": group.error,
            "min_price": group.min_price,
        }
        for group in response.groups
    }
    return {
        "id": case.id,
        "name": case.name,
        "query": case.query,
        "passed": passed,
        "took_ms": took_ms,
        "corrected": response.query.corrected,
        "notes": notes,
        "sources": sources,
        "total_products": sum(group.count for group in response.groups),
    }


def _print_report(results: list[dict], enabled: str) -> None:
    passed = sum(1 for item in results if item["passed"])
    print(f"\n{'=' * 72}")
    print(f"Smoke search: {passed}/{len(results)} passed | sources={enabled}")
    print(f"{'=' * 72}")
    for item in results:
        mark = "PASS" if item["passed"] else "FAIL"
        print(f"\n[{mark}] #{item['id']} {item['name']} — {item['query']!r} ({item['took_ms']} ms)")
        if item.get("corrected"):
            print(f"       corrected: {item['corrected']!r}")
        for source, meta in item.get("sources", {}).items():
            err = f" — {meta['error'][:50]}" if meta.get("error") else ""
            print(f"       {source}: {meta['count']} items{err}")
        for note in item.get("notes", []):
            print(f"       • {note}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run aggregator smoke tests")
    parser.add_argument("--quick", action="store_true", help="Disable Ozon for faster run")
    parser.add_argument("--ids", type=str, default="", help="Comma-separated case ids, e.g. 3,4,5")
    args = parser.parse_args()

    if args.quick:
        settings.search_enabled_sources = "wildberries,yandex_market,other"

    cases = SMOKE_CASES
    if args.ids.strip():
        wanted = {int(part.strip()) for part in args.ids.split(",") if part.strip()}
        cases = [case for case in SMOKE_CASES if case.id in wanted]

    enabled = settings.search_enabled_sources
    print(f"Running {len(cases)} smoke cases (sources={enabled})…")

    results: list[dict] = []
    for case in cases:
        print(f"\n→ #{case.id} {case.name}: {case.query!r}…")
        result = await _run_case(case)
        results.append(result)
        print(f"  {'OK' if result['passed'] else 'FAIL'} in {result['took_ms']}ms")

    _print_report(results, enabled)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "enabled_sources": enabled,
                "passed": sum(1 for item in results if item["passed"]),
                "total": len(results),
                "cases": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nReport: {REPORT_PATH}")

    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
