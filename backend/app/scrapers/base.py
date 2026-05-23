from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from app.core.models import Product, SearchRequest

PartialCallback = Callable[[list[Product]], Awaitable[None]]


class BaseScraper(ABC):
    source: str
    last_error: str | None = None
    last_source_status: str | None = None

    FAST_LIMIT: int = 5
    FULL_LIMIT: int = 15

    @abstractmethod
    async def search(
        self,
        request: SearchRequest,
        *,
        on_partial: PartialCallback | None = None,
    ) -> list[Product]:
        """Search products; call on_partial(first_batch) as soon as initial results are ready."""
        raise NotImplementedError

    def clear_error(self) -> None:
        self.last_error = None
        self.last_source_status = None

    def set_error(self, message: str | None) -> None:
        self.last_error = message

    def set_source_status(self, status: str | None) -> None:
        self.last_source_status = status
