from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class OtherSearchDiagnostics:
    query: str = ""
    live_provider: str = ""
    live_urls: int = 0
    live_sample: list[str] = field(default_factory=list)
    searxng_unresponsive: list[str] = field(default_factory=list)
    bing_errors: list[str] = field(default_factory=list)
    yahoo_errors: list[str] = field(default_factory=list)
    meili_hits: int = 0
    candidates_merged: int = 0
    candidates_ranked: int = 0
    fetch_ok: int = 0
    fetch_failed: int = 0
    extract_ok: int = 0
    extract_failed: int = 0
    failure_samples: list[str] = field(default_factory=list)
    timed_out: bool = False
    exception: str = ""

    def note_failure(self, message: str) -> None:
        if len(self.failure_samples) < 8:
            self.failure_samples.append(message)

    def _has_search_block(self) -> bool:
        for _, reason in self.searxng_unresponsive:
            lowered = reason.lower()
            if "captcha" in lowered or "too many requests" in lowered:
                return True
        return False

    def _has_transport_errors(self) -> bool:
        transport_markers = ("bad_decrypt", "ssl_", "ssl ", "tls", "connection", "timeout")
        all_errors = self.yahoo_errors + self.bing_errors
        return any(marker in error.lower() for error in all_errors for marker in transport_markers)

    def _detail_summary(self) -> str | None:
        details: list[str] = []
        if self._has_search_block():
            details.append("поисковики запросили CAPTCHA или включили ограничение по частоте")
        if self._has_transport_errors():
            details.append("часть источников ответила сетевой ошибкой")
        if self.live_urls > 0 and self.fetch_ok and self.extract_ok == 0:
            details.append("магазины не отдали карточки товаров в удобном для парсинга виде")
        if not details:
            return None
        return "Кратко: " + "; ".join(details) + "."

    def format_user_message(self) -> str:
        lines = ["Другие источники: 0 товаров."]

        if self.timed_out:
            lines.append("Внешний поиск отвечает слишком долго.")
        elif self.live_urls == 0 and self._has_search_block():
            lines.append("Внешние поисковики временно ограничили автоматические запросы.")
        elif self.live_urls == 0 and (
            self.yahoo_errors or self.bing_errors or self.searxng_unresponsive
        ):
            lines.append("Не удалось получить результаты из внешнего веб-поиска.")
        elif self.live_urls > 0 and self.extract_ok == 0:
            lines.append("Ссылки нашлись, но магазины не отдали подходящие карточки товаров.")
        elif self.exception:
            lines.append("Во время поиска произошла внешняя ошибка.")
        else:
            lines.append("Не удалось получить данные из внешних источников.")

        detail_summary = self._detail_summary()
        if detail_summary:
            lines.append(detail_summary)

        if self.live_urls == 0:
            lines.append("Попробуйте повторить запрос чуть позже.")

        return "\n".join(lines)


_current: ContextVar[OtherSearchDiagnostics | None] = ContextVar("other_diag", default=None)


def reset_diagnostics(query: str) -> OtherSearchDiagnostics:
    diag = OtherSearchDiagnostics(query=query)
    _current.set(diag)
    return diag


def get_diagnostics() -> OtherSearchDiagnostics | None:
    return _current.get()


def active_diagnostics() -> OtherSearchDiagnostics:
    diag = _current.get()
    if diag is None:
        diag = OtherSearchDiagnostics()
        _current.set(diag)
    return diag
