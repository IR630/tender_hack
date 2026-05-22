from dataclasses import dataclass

DEFAULT_REGION_ID = "moscow"


@dataclass(frozen=True, slots=True)
class Region:
    id: str
    name: str
    yandex_market_id: int
    wb_dest: int


REGIONS: dict[str, Region] = {
    "moscow": Region(
        id="moscow",
        name="Москва",
        yandex_market_id=213,
        wb_dest=-1257786,
    ),
    "spb": Region(
        id="spb",
        name="Санкт-Петербург",
        yandex_market_id=2,
        wb_dest=-1198059,
    ),
    "kazan": Region(
        id="kazan",
        name="Казань",
        yandex_market_id=43,
        wb_dest=-2133464,
    ),
    "ekaterinburg": Region(
        id="ekaterinburg",
        name="Екатеринбург",
        yandex_market_id=54,
        wb_dest=-5818943,
    ),
    "novosibirsk": Region(
        id="novosibirsk",
        name="Новосибирск",
        yandex_market_id=65,
        wb_dest=-364763,
    ),
}


def resolve_region(region_id: str | None) -> Region:
    if not region_id:
        return REGIONS[DEFAULT_REGION_ID]
    normalized = region_id.strip().lower()
    return REGIONS.get(normalized, REGIONS[DEFAULT_REGION_ID])


def list_regions() -> list[Region]:
    return list(REGIONS.values())
