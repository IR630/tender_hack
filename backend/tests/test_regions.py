from app.core.regions import DEFAULT_REGION_ID, resolve_region


def test_default_region_is_moscow() -> None:
    region = resolve_region(None)
    assert region.id == DEFAULT_REGION_ID
    assert region.name == "Москва"
    assert region.yandex_market_id == 213
    assert region.wb_dest == -1257786


def test_resolve_region_by_id() -> None:
    region = resolve_region("spb")
    assert region.id == "spb"
    assert region.name == "Санкт-Петербург"
    assert region.yandex_market_id == 2
    assert region.wb_dest == -1198059


def test_unknown_region_falls_back_to_moscow() -> None:
    region = resolve_region("unknown-city")
    assert region.id == DEFAULT_REGION_ID
