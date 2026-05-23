"""Smoke test suite metadata and evaluation helpers."""

from __future__ import annotations

from app.core.models import Product, SearchGroup, SearchQuery, SearchResponse, SearchSummary
from scripts.smoke_search import SMOKE_CASES, _evaluate, _validate_products


def _response_with_counts(counts: dict[str, int], *, errors: dict[str, str] | None = None) -> SearchResponse:
    errors = errors or {}
    groups = [
        SearchGroup(
            source=source,  # type: ignore[arg-type]
            display_name=source,
            count=count,
            error=errors.get(source),
            products=[
                Product(
                    source=source,  # type: ignore[arg-type]
                    source_domain=f"{source}.example",
                    title=f"Product from {source}",
                    price=100_000,
                    image_url="https://example.com/img.jpg",
                    product_url="https://example.com/p/1",
                )
            ]
            if count
            else [],
        )
        for source, count in counts.items()
    ]
    return SearchResponse(
        query=SearchQuery(
            original="test",
            corrected="test",
            region="moscow",
            region_name="Москва",
        ),
        summary=SearchSummary(total_found=sum(counts.values())),
        groups=groups,
    )


def test_smoke_cases_count():
    assert len(SMOKE_CASES) == 10


def test_smoke_case_ids_unique():
    ids = [case.id for case in SMOKE_CASES]
    assert len(ids) == len(set(ids))


def test_evaluate_passes_when_requirements_met():
    case = next(item for item in SMOKE_CASES if item.name == "ym_synonym_phone")
    response = _response_with_counts({"yandex_market": 10, "wildberries": 5, "other": 0})
    passed, notes = _evaluate(case, response, took_ms=5000)
    assert passed is True
    assert not notes or "sources ok" not in notes[0]


def test_evaluate_soft_pass_on_antibot():
    case = next(item for item in SMOKE_CASES if item.name == "headphones")
    response = _response_with_counts(
        {"yandex_market": 36, "wildberries": 0, "other": 0},
        errors={
            "wildberries": "HTTP 429: антибот Wildberries (rate-limit или IP).",
            "other": "Другие источники: 0 товаров.",
        },
    )
    passed, notes = _evaluate(case, response, took_ms=30_000)
    assert passed is True


def test_product_field_validator():
    response = _response_with_counts({"yandex_market": 1})
    assert _validate_products(response) == []
