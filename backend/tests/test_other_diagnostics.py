from other_public_scraper.diagnostics import OtherSearchDiagnostics, reset_diagnostics


def test_format_user_message_hides_technical_details() -> None:
    diag = reset_diagnostics("микронаушник")
    diag.yahoo_errors = ["curl: (56) Connection closed abruptly"]
    diag.searxng_unresponsive = [("google", "timeout")]

    message = diag.format_user_message()
    assert "curl" not in message
    assert "SearXNG" not in message
    assert "не удалось найти товары" in message


def test_format_user_message_when_extract_failed() -> None:
    diag = reset_diagnostics("ноутбук")
    diag.live_provider = "ddg"
    diag.live_urls = 3
    diag.extract_ok = 0
    diag.extract_failed = 2

    message = diag.format_user_message()
    assert "curl" not in message
    assert "не удалось извлечь" in message


def test_format_debug_message_keeps_technical_details() -> None:
    diag = reset_diagnostics("микронаушник")
    diag.yahoo_errors = ["curl: (56) Connection closed abruptly"]
    diag.searxng_unresponsive = [("google", "timeout")]

    debug = diag.format_debug_message()
    assert "curl" in debug
    assert "searxng" in debug
