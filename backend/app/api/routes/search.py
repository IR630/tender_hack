from fastapi import APIRouter

from app.core.models import SearchGroup, SearchQuery, SearchRequest, SearchResponse, SearchSummary
from app.orchestrator.search import run_search

router = APIRouter(prefix="/search", tags=["search"])

SOURCE_GROUPS: list[tuple[str, str]] = [
    ("wildberries", "Wildberries"),
    ("ozon", "Ozon"),
    ("yandex_market", "Яндекс Маркет"),
    ("other", "Другие источники"),
]


def _empty_response(query_text: str) -> SearchResponse:
    return SearchResponse(
        query=SearchQuery(
            original=query_text,
            corrected=query_text,
            synonyms_used=[],
            took_ms=0,
        ),
        summary=SearchSummary(),
        groups=[
            SearchGroup(source=source, display_name=display_name)  # type: ignore[arg-type]
            for source, display_name in SOURCE_GROUPS
        ],
    )


@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    return await run_search(request)


@router.post("/mock", response_model=SearchResponse, include_in_schema=False)
async def search_mock(request: SearchRequest) -> SearchResponse:
    return _empty_response(request.query)
