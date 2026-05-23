from other_public_scraper.diagnostics import OtherSearchDiagnostics, reset_diagnostics


def test_format_user_message_with_fetch_failures():
    diag = reset_diagnostics("ноутбук")
    diag.live_provider = "bing"
    diag.live_urls = 3
    diag.live_sample = ["https://www.dns-shop.ru/catalog", "https://www.mvideo.ru"]
    diag.candidates_ranked = 3
    diag.fetch_ok = 2
    diag.fetch_failed = 1
    diag.extract_ok = 0
    diag.extract_failed = 2
    diag.failure_samples = ["HTTP 401 — https://www.dns-shop.ru/catalog", "Нет title/price/image — mvideo"]

    message = diag.format_user_message()
    assert "0 товаров" in message
    assert "bing" in message.lower() or "Bing" in message or "bing" in message
    assert "401" in message
    assert "антибот" in message.lower() or "каталог" in message.lower()
