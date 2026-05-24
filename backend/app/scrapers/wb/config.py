from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v4/search"
BASKET_HOST_FMT = "https://basket-{host:02d}.wbbasket.ru"
PRODUCT_URL_FMT = "https://www.wildberries.ru/catalog/{nm}/detail.aspx"

MAX_RESULTS = settings.wb_max_results
BASKET_MIN, BASKET_MAX = 1, 50

HOST_HINT_RANGES: list[tuple[int, int]] = [
    (143, 1), (287, 2), (431, 3), (719, 4), (1007, 5), (1061, 6), (1115, 7),
    (1169, 8), (1313, 9), (1601, 10), (1655, 11), (1919, 12), (2045, 13),
    (2189, 14), (2405, 15), (2621, 16), (2837, 17), (3053, 18), (3269, 19),
    (3485, 20), (3701, 21), (3917, 22), (4193, 23), (4469, 24), (4877, 25),
    (5285, 26), (5693, 27), (6101, 28), (6509, 29), (6917, 30), (7325, 31),
    (7733, 32), (8141, 33), (8549, 34), (8957, 35), (9365, 36), (9773, 37),
    (10181, 38), (10589, 39), (10997, 40), (11405, 41), (11813, 42),
    (12221, 43), (12629, 44), (13037, 45), (13445, 46), (13853, 47),
    (14261, 48), (14669, 49), (15077, 50),
]

DEFAULT_BROWSER_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
    "x-userid": "0",
}


@dataclass(frozen=True, slots=True)
class WBUserPreset:
    """Preset profile for phase-4 VirtualUser pool (dest comes from regions.py)."""

    impersonate_profile: str
    user_agent: str
    spp: int


# Eight distinct combinations for the future user pool (phase 4).
WB_USER_PRESETS: tuple[WBUserPreset, ...] = (
    WBUserPreset(
        impersonate_profile="chrome120",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        spp=30,
    ),
    WBUserPreset(
        impersonate_profile="chrome124",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        spp=30,
    ),
    WBUserPreset(
        impersonate_profile="chrome131",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        spp=31,
    ),
    WBUserPreset(
        impersonate_profile="chrome120",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        ),
        spp=29,
    ),
    WBUserPreset(
        impersonate_profile="chrome124",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
        ),
        spp=28,
    ),
    WBUserPreset(
        impersonate_profile="chrome131",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
        ),
        spp=27,
    ),
    WBUserPreset(
        impersonate_profile="chrome120",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        spp=26,
    ),
    WBUserPreset(
        impersonate_profile="chrome131",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        ),
        spp=25,
    ),
)

DEFAULT_WB_PRESET = WB_USER_PRESETS[2]
