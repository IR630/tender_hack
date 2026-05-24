from other_public_scraper.diagnostics import reset_diagnostics


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
    diag.failure_samples = [
        "HTTP 401 — https://www.dns-shop.ru/catalog",
        "Нет title/price/image — mvideo",
    ]

    message = diag.format_user_message()
    assert "0 товаров" in message
    assert "Ссылки нашлись" in message
    assert "магазины не отдали" in message


def test_format_user_message_with_captcha_and_transport_errors():
    diag = reset_diagnostics("швабра")
    diag.yahoo_errors = [
        "query: Failed to perform, curl: (56) BoringSSL SSL_read: BAD_DECRYPT"
    ]
    diag.searxng_unresponsive = [
        ("duckduckgo", "CAPTCHA"),
        ("google", "Suspended: CAPTCHA"),
        ("brave", "Suspended: too many requests"),
    ]

    message = diag.format_user_message()
    assert "0 товаров" in message
    assert "ограничили автоматические запросы" in message
    assert "Кратко:" in message
    assert "сетевой ошибкой" in message
    assert "Попробуйте повторить запрос чуть позже." in message
