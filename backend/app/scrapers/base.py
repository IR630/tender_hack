from abc import ABC, abstractmethod

from app.core.models import Product, SearchRequest


class BaseScraper(ABC):
    source: str
    last_error: str | None = None
    last_source_status: str | None = None

    @abstractmethod
    async def search(self, request: SearchRequest) -> list[Product]:
        raise NotImplementedError

    def clear_error(self) -> None:
        self.last_error = None
        self.last_source_status = None

    def set_error(self, message: str | None) -> None:
        self.last_error = message

    def set_source_status(self, status: str | None) -> None:
        self.last_source_status = status
