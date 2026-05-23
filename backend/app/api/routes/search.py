from fastapi import APIRouter, HTTPException

from app.core.models import (
    SearchGroup,
    SearchRequest,
    SearchResponse,
    SearchTaskCreateResponse,
    SearchTaskStatusResponse,
)
from app.core.regions import resolve_region
from app.orchestrator.search import spawn_search_task
from app.tasks.store import search_task_store

router = APIRouter(prefix="/search", tags=["search"])

SOURCE_GROUPS: list[tuple[str, str]] = [
    ("wildberries", "Wildberries"),
    ("ozon", "Ozon"),
    ("yandex_market", "Яндекс Маркет"),
    ("other", "Другие источники"),
]


def _empty_response(query_text: str, region_id: str = "moscow") -> SearchResponse:
    from app.core.models import SearchQuery, SearchSummary

    region = resolve_region(region_id)
    return SearchResponse(
        query=SearchQuery(
            original=query_text,
            corrected=query_text,
            region=region.id,
            region_name=region.name,
            synonyms_used=[],
            took_ms=0,
        ),
        summary=SearchSummary(),
        groups=[
            SearchGroup(source=source, display_name=display_name)  # type: ignore[arg-type]
            for source, display_name in SOURCE_GROUPS
        ],
    )


@router.post("", response_model=SearchTaskCreateResponse)
async def search_start(request: SearchRequest) -> SearchTaskCreateResponse:
    """Start async search; poll GET /search/{task_id} every ~3s."""
    task_id = await search_task_store.create()
    spawn_search_task(task_id, request)
    return SearchTaskCreateResponse(task_id=task_id)


@router.get("/{task_id}", response_model=SearchTaskStatusResponse)
async def search_status(task_id: str) -> SearchTaskStatusResponse:
    task = await search_task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return SearchTaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        message=task.message,
        error=task.error,
        result=task.result,
        groups=task.groups,
    )


@router.post("/sync", response_model=SearchResponse, include_in_schema=False)
async def search_sync(request: SearchRequest) -> SearchResponse:
    """Blocking search (dev/debug). Prefer POST /search + polling."""
    from app.orchestrator.search import run_search

    return await run_search(request)


@router.post("/mock", response_model=SearchResponse, include_in_schema=False)
async def search_mock(request: SearchRequest) -> SearchResponse:
    return _empty_response(request.query, request.region)
