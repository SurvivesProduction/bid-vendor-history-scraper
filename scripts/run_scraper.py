#!/usr/bin/env python
"""Example end-to-end run of the bidscraper framework.

This is a template/demo, NOT a real scraper. `ExampleStaticScraper` below
fetches from a small hardcoded in-memory dataset instead of a real portal,
to demonstrate how a concrete `BaseScraper` subclass plugs into
fetch -> parse -> normalize -> upsert. Real portal scrapers belong in a
downstream client deployment package (e.g. `bidscraper_full.scrapers`).

Usage:
    python scripts/run_scraper.py --client-id demo
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv

from bidscraper.db.client import get_connection, upsert_bid_award
from bidscraper.normalize.schema import BidAward
from bidscraper.scrapers.base import BaseScraper

_EXAMPLE_SOURCE = "example-static-source"

# A tiny hardcoded fake dataset standing in for a real scraped portal.
_EXAMPLE_RAW_RECORDS: list[dict[str, Any]] = [
    {
        "id": "EX-001",
        "agency": "Example County Public Works",
        "title": "Annual Road Resurfacing Contract",
        "description": "Resurfacing of approximately 12 miles of county roads.",
        "vendor": "Acme Paving Co.",
        "award_date": "2026-01-15",
        "value": "185000.00",
        "term_end": "2027-01-15",
    },
    {
        "id": "EX-002",
        "agency": "Example County Public Works",
        "title": "Electrical Maintenance Services",
        "description": "On-call electrical maintenance for county facilities.",
        "vendor": "Bright Spark Electric LLC",
        "award_date": "2026-02-01",
        "value": "92000.00",
        "term_end": "2027-02-01",
    },
]


class ExampleStaticScraper(BaseScraper):
    """Template scraper demonstrating the `BaseScraper` interface.

    Reads from a hardcoded in-memory list instead of a real portal. Use
    this as a reference for what fetch/parse/normalize should look like
    in a real subclass -- do not point this at a real target as-is.
    """

    def fetch(self) -> list[dict[str, Any]]:
        return _EXAMPLE_RAW_RECORDS

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw

    def normalize(self, raw_record: dict[str, Any]) -> BidAward:
        return BidAward(
            client_id=self.client_id,
            source=self.source,
            source_record_id=raw_record["id"],
            awarding_agency=raw_record["agency"],
            project_title=raw_record["title"],
            project_description=raw_record.get("description"),
            awarded_vendor=raw_record["vendor"],
            award_date=date.fromisoformat(raw_record["award_date"]),
            contract_value=Decimal(raw_record["value"]),
            contract_term_end=date.fromisoformat(raw_record["term_end"]),
            raw_data=raw_record,
        )


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the example bidscraper demo scraper.")
    parser.add_argument("--client-id", required=True, help="Client id to tag records with.")
    args = parser.parse_args()

    scraper = ExampleStaticScraper(client_id=args.client_id, source=_EXAMPLE_SOURCE)

    conn = get_connection()
    try:
        processed = 0
        for bid in scraper.run():
            row = upsert_bid_award(conn, bid)
            processed += 1
            print(f"Upserted: {row['project_title']} -> {row['awarded_vendor']} (id={row['id']})")
        print(f"Done. Processed {processed} record(s).")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
