from __future__ import annotations

import pytest

from app.scrapers import ozon_browser

WAF_BLOCK_HTML = """
<!DOCTYPE html><html lang="ru"><head>
<title>Доступ ограничен</title>
<link rel="stylesheet" href="https://cdn2.ozone.ru/s3/abt-challenge/incidents/styles_v2/common.css">
</head><body><div class="title">Похоже, нет&nbsp;соединения</div>
<div class="inc">Инцидент: fab_20260523231111_01KSBHPQBHXEMJA71NF0RSYJ1D</div></body></html>
"""


def test_is_challenge_detects_waf_block_page() -> None:
    assert ozon_browser.is_challenge(WAF_BLOCK_HTML) is True


def test_browser_headless_defaults_false() -> None:
    assert ozon_browser._browser_headless() is False


def _search_html(count: int) -> str:
    cards = []
    for index in range(count):
        cards.append(
            f"""
            <div class="tile-root">
              <a href="/product/pencil-{index}/">
                <span class="tsBody500Medium">Карандаши цветные {index}</span>
              </a>
              <img srcset="https://ir.ozone.ru/s3/{index}.jpg 2x">
              <span>{100 + index} ₽</span>
            </div>
            """
        )
    return f'<div data-widget="tileGridDesktop">{"".join(cards)}</div>'


class FakeSearchTab:
    def __init__(self, initial_count: int = 2) -> None:
        self.html = _search_html(initial_count)
        self.scrolls = 0

    async def get_content(self) -> str:
        return self.html

    async def sleep(self, seconds: float) -> None:
        return None

    async def scroll_down(self, amount: int) -> None:
        self.scrolls += 1
        self.html = _search_html(15)


class FakeSearchBrowser:
    def __init__(self, tab: FakeSearchTab) -> None:
        self.tab = tab

    async def get(self, url: str) -> FakeSearchTab:
        return self.tab


@pytest.mark.asyncio
async def test_navigate_search_scrolls_until_target_products(monkeypatch) -> None:
    tab = FakeSearchTab()
    browser = FakeSearchBrowser(tab)
    monkeypatch.setattr(ozon_browser.settings, "ozon_browser_scroll_rounds", 1)
    monkeypatch.setattr(ozon_browser.settings, "ozon_browser_scroll_pause_seconds", 0)
    monkeypatch.setattr(ozon_browser.settings, "ozon_browser_max_results", 20)
    monkeypatch.setattr(ozon_browser.settings, "search_max_results_per_source", 15)

    html, error = await ozon_browser.navigate_and_get_html(
        browser,  # type: ignore[arg-type]
        "https://www.ozon.ru/search/?text=test",
        wait_seconds=1,
        require_products=True,
    )

    products = ozon_browser.extract_products(html, max_results=20)
    assert error is None
    assert len(products) == 15
    assert tab.scrolls == 1


@pytest.mark.asyncio
async def test_navigate_search_emits_initial_products_before_scroll(monkeypatch) -> None:
    tab = FakeSearchTab(initial_count=5)
    browser = FakeSearchBrowser(tab)
    emitted_counts: list[int] = []
    monkeypatch.setattr(ozon_browser.settings, "ozon_browser_scroll_rounds", 1)
    monkeypatch.setattr(ozon_browser.settings, "ozon_browser_scroll_pause_seconds", 0)
    monkeypatch.setattr(ozon_browser.settings, "ozon_browser_max_results", 20)
    monkeypatch.setattr(ozon_browser.settings, "search_max_results_per_source", 15)

    async def on_products_html(html: str) -> None:
        emitted_counts.append(len(ozon_browser.extract_products(html, max_results=20)))

    html, error = await ozon_browser.navigate_and_get_html(
        browser,  # type: ignore[arg-type]
        "https://www.ozon.ru/search/?text=test",
        wait_seconds=1,
        require_products=True,
        on_products_html=on_products_html,
    )

    products = ozon_browser.extract_products(html, max_results=20)
    assert error is None
    assert emitted_counts == [5]
    assert len(products) == 15


@pytest.mark.asyncio
async def test_navigate_search_waits_for_five_before_partial(monkeypatch) -> None:
    tab = FakeSearchTab(initial_count=2)
    browser = FakeSearchBrowser(tab)
    emitted_counts: list[int] = []
    monkeypatch.setattr(ozon_browser.settings, "ozon_browser_scroll_rounds", 1)
    monkeypatch.setattr(ozon_browser.settings, "ozon_browser_scroll_pause_seconds", 0)
    monkeypatch.setattr(ozon_browser.settings, "ozon_browser_max_results", 20)
    monkeypatch.setattr(ozon_browser.settings, "search_max_results_per_source", 15)

    async def on_products_html(html: str) -> None:
        emitted_counts.append(len(ozon_browser.extract_products(html, max_results=20)))

    html, error = await ozon_browser.navigate_and_get_html(
        browser,  # type: ignore[arg-type]
        "https://www.ozon.ru/search/?text=test",
        wait_seconds=1,
        require_products=True,
        on_products_html=on_products_html,
    )

    products = ozon_browser.extract_products(html, max_results=20)
    assert error is None
    assert emitted_counts == [15]
    assert len(products) == 15
