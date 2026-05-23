from __future__ import annotations

from other_public_scraper.config import settings


class LLMClient:
    async def validate(self, text: str, query: str) -> bool:
        _ = (text, query)
        if not settings.other_llm_enabled:
            return True
        return True

    async def extract_product(self, text: str, query: str) -> dict | None:
        _ = (text, query)
        return None
