from app.scrapers.wb.proxy import build_proxy_dict, proxy_url_from_raw


def test_proxy_url_from_raw_key_format(monkeypatch):
    monkeypatch.setattr("app.scrapers.wb.proxy.settings.wb_proxy_sticky_session", False)
    assert proxy_url_from_raw("pool.proxy.market:10000@user:pass") == (
        "http://user:pass@pool.proxy.market:10000"
    )
    monkeypatch.setattr(
        "app.scrapers.wb.proxy.settings.wb_proxy",
        "pool.proxy.market:10000@user:pass",
    )
    assert build_proxy_dict() == {
        "http": "http://user:pass@pool.proxy.market:10000",
        "https": "http://user:pass@pool.proxy.market:10000",
    }


def test_proxy_url_sticky_session(monkeypatch):
    monkeypatch.setattr("app.scrapers.wb.proxy.settings.wb_proxy_sticky_session", True)
    assert proxy_url_from_raw("pool.proxy.market:10000@user:pass", session_id="abc123") == (
        "http://user-session-abc123:pass@pool.proxy.market:10000"
    )


def test_proxy_url_from_raw_http_url():
    assert proxy_url_from_raw("http://user:pass@host:8080") == "http://user:pass@host:8080"


def test_build_proxy_dict_empty(monkeypatch):
    monkeypatch.setattr("app.scrapers.wb.proxy.settings.wb_proxy", "")
    assert build_proxy_dict() is None
