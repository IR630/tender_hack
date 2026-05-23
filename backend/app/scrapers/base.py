from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.core.models import Product, SearchRequest


@dataclass
class ScraperResult:
    products: list[Product] = field(default_factory=list)
    error: str | None = None


class BaseScraper(ABC):
    source: str
    last_error: str | None = None

    @abstractmethod
    async def search(self, request: SearchRequest) -> list[Product]:
        raise NotImplementedError

    def clear_error(self) -> None:
        self.last_error = None

    def set_error(self, message: str | None) -> None:
        self.last_error = message
