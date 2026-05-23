from __future__ import annotations

from typing import Protocol


class DomainAdapter(Protocol):
    domain: str

    def supports(self, url: str) -> bool: ...

    def extract(self, html: str, url: str) -> dict: ...


def get_adapter(url: str):
    from other_public_scraper.parsers.adapters import (
        chetyre_tochki,
        citilink,
        dns_shop,
        koleso,
        lamoda,
        mvideo,
        notik,
    )

    for module in (dns_shop, citilink, mvideo, notik, chetyre_tochki, koleso, lamoda):
        adapter = module.adapter
        if adapter.supports(url):
            return adapter
    return None
