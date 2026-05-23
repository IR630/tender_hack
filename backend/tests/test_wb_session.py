import pytest

from app.core.config import settings
from app.scrapers.wb.session import WBSession


@pytest.mark.asyncio
async def test_needs_warmup_when_no_session():
    session = WBSession(user_id="test")
    assert session.needs_warmup() is True


@pytest.mark.asyncio
async def test_needs_warmup_false_when_fresh(monkeypatch):
    monkeypatch.setattr(settings, "wb_warmup_enabled", True)
    session = WBSession(user_id="test")
    session._session = object()  # noqa: SLF001
    session._warmed = True
    session.created_at = 1000.0
    session.last_used = 1000.0
    monkeypatch.setattr("app.scrapers.wb.session.time.monotonic", lambda: 1001.0)
    assert session.needs_warmup() is False


@pytest.mark.asyncio
async def test_needs_warmup_when_session_too_old(monkeypatch):
    monkeypatch.setattr(settings, "wb_warmup_enabled", True)
    monkeypatch.setattr(settings, "wb_session_max_age_seconds", 60.0)
    session = WBSession(user_id="test")
    session._session = object()  # noqa: SLF001
    session._warmed = True
    session.created_at = 1000.0
    session.last_used = 1000.0
    monkeypatch.setattr("app.scrapers.wb.session.time.monotonic", lambda: 1100.0)
    assert session.needs_warmup() is True


@pytest.mark.asyncio
async def test_warmup_disabled_skips_needs_warmup(monkeypatch):
    monkeypatch.setattr(settings, "wb_warmup_enabled", False)
    session = WBSession(user_id="test")
    assert session.needs_warmup() is False
