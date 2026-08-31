"""Abstract base class every portal-specific scraper implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from bidscraper.normalize.schema import BidAward


class BaseScraper(ABC):
    """Defines the fetch -> parse -> normalize -> yield pipeline shape.

    Concrete subclasses live in a downstream package (e.g. the paid
    per-client deployment) and are parametrized per portal / client. This
    class has no knowledge of any specific scraping target.
    """

    def __init__(self, client_id: str, source: str) -> None:
        self.client_id = client_id
        self.source = source

    @abstractmethod
    def fetch(self) -> Any:
        """Retrieve the raw content for this source (HTML, JSON, etc.)."""
        raise NotImplementedError

    @abstractmethod
    def parse(self, raw: Any) -> list[dict[str, Any]]:
        """Parse raw fetched content into a list of raw record dicts."""
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_record: dict[str, Any]) -> BidAward:
        """Convert a single raw record dict into a `BidAward`."""
        raise NotImplementedError

    def run(self) -> Iterator[BidAward]:
        """Orchestrate fetch -> parse -> normalize -> yield `BidAward` records."""
        raw = self.fetch()
        for raw_record in self.parse(raw):
            yield self.normalize(raw_record)
