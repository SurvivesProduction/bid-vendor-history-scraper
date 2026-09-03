"""Generic, client-agnostic SQL-backed insight queries.

Nothing in this module encodes any client-specific business logic -- it's
pure SQL over the shared `bid_awards` schema, parametrized by client_id.
"""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row


def vendor_win_counts(
    conn: psycopg.Connection,
    client_id: str,
    source: str | None = None,
    category_keyword: str | None = None,
) -> list[dict[str, Any]]:
    """Return vendors ordered by number of bid awards won, descending.

    Each result row is `{"awarded_vendor": str, "win_count": int}`.
    Pass `source` to restrict the count to a single data source.

    Pass `category_keyword` to scope the count to awards whose
    `project_title` OR `awarded_vendor` contains that text
    (case-insensitive substring match, either field) -- a generic way to
    break the leaderboard down by category when a source's data carries a
    real, meaningful keyword signal (e.g. a trade name). Checking BOTH
    fields matters: a real category can be signaled by the vendor's own
    name even when the specific project's title doesn't mention the trade
    at all (e.g. "Stadium Sound System" won by an electrical contractor
    whose other work is clearly electrical, but whose title alone gives
    no hint) -- title-only matching silently misses those. This module
    stays client-agnostic: it takes whatever keyword a caller supplies
    rather than hardcoding any category of its own -- a client-specific
    category definition (which keyword means what to that client, and
    any judgment calls about ambiguous matches) belongs in that client's
    own insight code, not here.

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
          and (
            %(category_keyword)s::text is null
            or ba.project_title ilike '%%' || %(category_keyword)s || '%%'
            or ba.awarded_vendor ilike '%%' || %(category_keyword)s || '%%'
          )
        group by coalesce(va.canonical_name, ba.awarded_vendor)
        order by win_count desc, awarded_vendor asc
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            query,
            {"client_id": client_id, "source": source, "category_keyword": category_keyword},
        )
        return cur.fetchall()
