from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from ozon_public_scraper.parsers.json_ld import extract_product_from_json_ld
from ozon_public_scraper.parsers.og_extractor import extract_og


class NotikAdapter:
    domain = "notik.ru"

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
        if data.get("price_rub") is None:
            match = re.search(r'itemprop="price"[^>]*content="(\d+)"', html)
            if match:
                data["price_rub"] = int(match.group(1))
        image_url = str(data.get("image_url") or "").strip()
        if image_url and not image_url.startswith("http"):
            data["image_url"] = urljoin(url, image_url)
        data["extraction_method"] = "adapter:notik.ru"
        data["confidence"] = 1.0
        return data


adapter = NotikAdapter()
