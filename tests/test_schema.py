from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from bidscraper.normalize.schema import BidAward


def test_bid_award_accepts_full_valid_record() -> None:
    bid = BidAward(
        client_id="demo",
        source="example-source",
        source_record_id="ABC-123",
        awarding_agency="Example County",
        project_title="Road Resurfacing",
        project_description="Resurface roads",
        awarded_vendor="Acme Paving",
        award_date=date(2026, 1, 15),
        contract_value=Decimal("185000.00"),
        contract_term_end=date(2027, 1, 15),
        raw_data={"id": "ABC-123"},
    )
    assert bid.client_id == "demo"
    assert bid.contract_value == Decimal("185000.00")


def test_bid_award_allows_optional_fields_to_be_omitted() -> None:
    bid = BidAward(
        client_id="demo",
        source="example-source",
        awarding_agency="Example County",
        project_title="Road Resurfacing",
        awarded_vendor="Acme Paving",
    )
    assert bid.source_record_id is None
    assert bid.award_date is None
    assert bid.contract_value is None
    assert bid.raw_data == {}


def test_bid_award_requires_core_fields() -> None:
    with pytest.raises(ValidationError):
        BidAward(client_id="demo", source="example-source")
