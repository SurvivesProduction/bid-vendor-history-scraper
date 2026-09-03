"""Generic, client-agnostic SQL-backed insight queries.

Nothing in this module encodes any client-specific business logic -- it's
pure SQL over the shared `bid_awards` schema, parametrized by client_id.
"""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row


def vendor_win_counts(
    conn: psycopg.Connection, client_id: str, source: str | None = None
) -> list[dict[str, Any]]:
    """Return vendors ordered by number of bid awards won, descending.

    Each result row is `{"awarded_vendor": str, "win_count": int}`.
    Pass `source` to restrict the count to a single data source.

    Rows flagged `needs_review` are excluded -- a row awaiting review
    (whether because of dedup ambiguity or, per a scraper's own
    judgment, because the source document didn't clearly identify a
    vendor) shouldn't count as a confirmed win until it's resolved.

    Groups by canonical vendor name where one is known (via a left join
    against `vendor_aliases`, populated by
    `bidscraper.db.vendor_aliases.backfill_vendor_aliases`), falling back
    to the raw `awarded_vendor` string for anything not yet resolved --
    so the same real vendor recorded under several spellings (e.g. "CT
    Electric Corp" / "CT Electric Corp." / "CT Electrical Corp") counts
    as one vendor instead of three. This is a plain left join, not a
    hard dependency: running with an empty/no `vendor_aliases` table
    degrades gracefully to grouping by the raw string, same as before
    that table existed.
    """
    query = """
        select coalesce(va.canonical_name, ba.awarded_vendor) as awarded_vendor, count(*) as win_count
        from bid_awards ba
        left join vendor_aliases va
          on va.client_id = ba.client_id and va.raw_name = ba.awarded_vendor
        where ba.client_id = %(client_id)s
          and ba.awarded_vendor is not null
          and ba.needs_review = false
          and (%(source)s::text is null or ba.source = %(source)s)
        group by coalesce(va.canonical_name, ba.awarded_vendor)
        order by win_count desc, awarded_vendor asc
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, {"client_id": client_id, "source": source})
        return cur.fetchall()
