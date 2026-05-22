from fastapi import APIRouter

from app.core.regions import list_regions

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("")
async def get_regions() -> list[dict[str, str]]:
    return [{"id": region.id, "name": region.name} for region in list_regions()]
