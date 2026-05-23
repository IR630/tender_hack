from __future__ import annotations

from urllib.parse import urlparse

from ozon_public_scraper.parsers.json_ld import extract_product_from_json_ld
from ozon_public_scraper.parsers.og_extractor import extract_og


class MvideoAdapter:
    domain = "mvideo.ru"

    def supports(self, url: str) -> bool:
        host = urlparse(url).netloc.lower().replace("www.", "")
        return host == self.domain or host.endswith("." + self.domain)

    def extract(self, html: str, url: str) -> dict:
        data = extract_product_from_json_ld(html)
        if not data.get("title"):
            og = extract_og(html, url=url)
            if og.title:
                data["title"] = og.title
            if og.description:
                data["description"] = og.description
            if og.image_url:
                data["image_url"] = og.image_url
            if og.price_rub:
                data["price_rub"] = og.price_rub
        data["extraction_method"] = "adapter:mvideo.ru"
        data["confidence"] = 1.0
        return data


adapter = MvideoAdapter()
