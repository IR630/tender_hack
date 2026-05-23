from dataclasses import dataclass

DEFAULT_REGION_ID = "moscow"


@dataclass(frozen=True, slots=True)
class Region:
    id: str
    name: str
    yandex_market_id: int
    wb_dest: int
    ozon_city_name: str   # city name as shown in Ozon's location UI
    search_keyword: str   # city keyword appended to search queries in "other" sources


REGIONS: dict[str, Region] = {
    "moscow":    Region("moscow", "Москва", 213, -1257786, "Москва", "Москва"),
    "spb":       Region("spb", "Санкт-Петербург", 2, -1198059, "Санкт-Петербург", "СПб"),
    "kazan":     Region("kazan", "Казань", 43, -2133464, "Казань", "Казань"),
    "ekaterinburg": Region("ekaterinburg", "Екатеринбург", 54, -5818943, "Екатеринбург", "Екатеринбург"),
    "novosibirsk":  Region("novosibirsk", "Новосибирск", 65, -364763, "Новосибирск", "Новосибирск"),
}


def resolve_region(region_id: str | None) -> Region:
    if not region_id:
        return REGIONS[DEFAULT_REGION_ID]
    normalized = region_id.strip().lower()
    return REGIONS.get(normalized, REGIONS[DEFAULT_REGION_ID])


def list_regions() -> list[Region]:
    return list(REGIONS.values())
