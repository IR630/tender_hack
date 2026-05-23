from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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
        if self.timed_out:
            return (
                "Другие источники: поиск занял слишком много времени. "
                "Попробуйте упростить запрос или повторите позже."
            )
        if self.live_urls == 0:
            return (
                "Другие источники: не удалось найти товары на сторонних сайтах. "
                "Попробуйте другой запрос или повторите поиск позже."
            )
        if self.extract_ok == 0:
            return (
                "Другие источники: сайты найдены, но не удалось извлечь товары "
                "(антибот или нестандартная вёрстка). Попробуйте другой запрос."
            )
        return (
            "Другие источники: не удалось собрать достаточно товаров. "
            "Попробуйте уточнить запрос."
        )

    def format_debug_message(self) -> str:
        lines = [f"query={self.query!r}"]

        if self.timed_out:
            lines.append("timed_out=true")
        if self.exception:
            lines.append(f"exception={self.exception}")
        if self.yahoo_errors:
            lines.append(f"yahoo={self.yahoo_errors[0]}")
        if self.bing_errors:
            lines.append(f"bing={self.bing_errors[0]}")
        if self.searxng_unresponsive:
            engines = ", ".join(f"{e[0]}({e[1]})" for e in self.searxng_unresponsive[:4])
            lines.append(f"searxng={engines}")
        if self.live_urls:
            lines.append(f"live_urls={self.live_urls} provider={self.live_provider}")
        if self.candidates_ranked:
            lines.append(
                f"ranked={self.candidates_ranked} fetch_ok={self.fetch_ok} "
                f"fetch_failed={self.fetch_failed} extract_ok={self.extract_ok} "
                f"extract_failed={self.extract_failed}"
            )
        if self.failure_samples:
            lines.append("failures=" + " | ".join(self.failure_samples[:3]))
        return "; ".join(lines)

    def log_debug(self) -> None:
        logger.info("other_search_diagnostics %s", self.format_debug_message())


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
