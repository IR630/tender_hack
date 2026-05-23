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

    def format_user_message(self) -> str:
        lines = ["Другие источники: 0 товаров. Диагностика:"]

        if self.timed_out:
            lines.append(f"• Таймаут поиска ({self.query!r})")
        if self.exception:
            lines.append(f"• Ошибка: {self.exception}")

        if self.live_urls == 0:
            if self.yahoo_errors:
                lines.append(f"• Yahoo: {self.yahoo_errors[0]}")
            if self.bing_errors:
                lines.append(f"• Bing: {self.bing_errors[0]}")
            if self.searxng_unresponsive:
                engines = ", ".join(f"{e[0]}({e[1]})" for e in self.searxng_unresponsive[:4])
                lines.append(f"• SearXNG: движки недоступны — {engines}")
            if not self.yahoo_errors and not self.bing_errors and not self.searxng_unresponsive:
                lines.append("• Веб-поиск не вернул URL (проверьте SearXNG/интернет/VPN)")
        else:
            provider = self.live_provider or "web"
            lines.append(f"• Поиск ({provider}): найдено {self.live_urls} URL")
            for url in self.live_sample[:3]:
                lines.append(f"  → {url}")

        if self.candidates_ranked:
            lines.append(
                f"• Обработка: {self.candidates_ranked} URL → "
                f"скачано {self.fetch_ok}, ошибок fetch {self.fetch_failed}, "
                f"извлечено {self.extract_ok}, отфильтровано {self.extract_failed}"
            )

        if self.failure_samples:
            lines.append("• Примеры отказов:")
            for sample in self.failure_samples[:5]:
                lines.append(f"  — {sample}")

        if self.extract_failed and self.fetch_ok and self.extract_ok == 0:
            lines.append(
                "• Вероятная причина: антибот (401/429) или каталог без цены в HTML"
            )

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
