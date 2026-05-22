from abc import ABC, abstractmethod

from app.core.models import Product, SearchRequest


class BaseScraper(ABC):
    source: str

    @abstractmethod
    async def search(self, request: SearchRequest) -> list[Product]:
        raise NotImplementedError
