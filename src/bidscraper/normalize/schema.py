"""The normalized output contract every scraper must produce."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BidAward(BaseModel):
    """A normalized bid-award record produced by a scraper.

    This is the scraper's output contract: `BaseScraper.normalize()` must
    return instances of this model. Fields that only matter at the
    database-insert layer -- record_key, dedup_method, match_confidence,
    needs_review -- are deliberately NOT part of this model. Those are
    computed by `bidscraper.db.client` when a record is upserted, not by
    the scraper itself.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    client_id: str
    source: str
    source_record_id: str | None = None
    awarding_agency: str
    project_title: str
    project_description: str | None = None
    awarded_vendor: str
    award_date: date | None = None
    contract_value: Decimal | None = None
    contract_term_end: date | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
