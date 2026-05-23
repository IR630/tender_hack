from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from curl_cffi.requests import AsyncSession

from app.core.config import settings

if TYPE_CHECKING:
    pass

_IP_CHECK_URLS = (
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://httpbin.org/ip",
)

_exit_ip_cache: str | None = None
_exit_ip_fetched_at = 0.0
_EXIT_IP_TTL = 60.0


def _split_user_pass(user_pass: str) -> tuple[str, str]:
    user, sep, password = user_pass.partition(":")
    if not sep:
        return user_pass, ""
    return user, password


def proxy_url_from_raw(raw: str, *, session_id: str | None = None) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://", "socks5://")):
        return raw
    # pool.proxy.market:10000@user:pass → http://user:pass@host:port
    host_port, _, user_pass = raw.partition("@")
    if not host_port or not user_pass:
        return None
    user, password = _split_user_pass(user_pass)
    if session_id and settings.wb_proxy_sticky_session:
        user = f"{user}-session-{session_id}"
    return f"http://{user}:{password}@{host_port}"


def build_proxy_dict(*, session_id: str | None = None) -> dict[str, str] | None:
    url = proxy_url_from_raw(settings.wb_proxy, session_id=session_id)
    if not url:
        return None
    return {"http": url, "https": url}


def proxy_is_configured() -> bool:
    return build_proxy_dict() is not None


async def get_exit_ip(session: AsyncSession) -> str:
    """Return outbound IP for the given session (cached 60 s)."""
    global _exit_ip_cache, _exit_ip_fetched_at
    now = time.monotonic()
    if _exit_ip_cache and now - _exit_ip_fetched_at < _EXIT_IP_TTL:
        return _exit_ip_cache

    ip = "unavailable"
    for url in _IP_CHECK_URLS:
        try:
            response = await session.get(url, timeout=5)
            text = response.text.strip()
            if text.startswith("{"):
                ip = json.loads(text).get("origin", "unknown")
            else:
                ip = text
            break
        except Exception:
            continue

    _exit_ip_cache = ip
    _exit_ip_fetched_at = now
    return ip


def reset_exit_ip_cache() -> None:
    global _exit_ip_cache, _exit_ip_fetched_at
    _exit_ip_cache = None
    _exit_ip_fetched_at = 0.0
