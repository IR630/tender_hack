from __future__ import annotations

from app.scrapers import ozon_browser

WAF_BLOCK_HTML = """
<!DOCTYPE html><html lang="ru"><head>
<title>Доступ ограничен</title>
<link rel="stylesheet" href="https://cdn2.ozone.ru/s3/abt-challenge/incidents/styles_v2/common.css">
</head><body><div class="title">Похоже, нет&nbsp;соединения</div>
<div class="inc">Инцидент: fab_20260523231111_01KSBHPQBHXEMJA71NF0RSYJ1D</div></body></html>
"""

HOME_HTML = "<html><head><title>Ozon</title></head><body>" + ("x" * 20_000) + "</body></html>"


def test_is_challenge_detects_waf_block_page() -> None:
    assert ozon_browser.is_challenge(WAF_BLOCK_HTML) is True


def test_is_warmup_ready_accepts_large_homepage() -> None:
    assert ozon_browser._is_warmup_ready(HOME_HTML) is True


def test_is_warmup_ready_rejects_waf_block() -> None:
    assert ozon_browser._is_warmup_ready(WAF_BLOCK_HTML) is False


def test_browser_headless_defaults_false() -> None:
    assert ozon_browser._browser_headless() is False
