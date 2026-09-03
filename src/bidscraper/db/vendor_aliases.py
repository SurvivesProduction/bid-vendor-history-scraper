"""DB I/O for vendor-name canonicalization.

Reads/writes the `vendor_aliases` table using the pure matching logic in
`bidscraper.normalize.vendor_alias`. See that module's docstring for the
problem this solves and the matching rationale.
"""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from bidscraper.normalize.vendor_alias import (
    classify_match,
    find_best_match,
    normalize_vendor_name,
)


def _get_existing_alias(conn: psycopg.Connection, client_id: str, raw_name: str) -> dict[str, Any] | None:
    query = """
        select * from vendor_aliases
        where client_id = %(client_id)s and raw_name = %(raw_name)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, {"client_id": client_id, "raw_name": raw_name})
        return cur.fetchone()


def _get_canonical_names(conn: psycopg.Connection, client_id: str) -> list[str]:
    query = "select distinct canonical_name from vendor_aliases where client_id = %(client_id)s"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, {"client_id": client_id})
        return [row["canonical_name"] for row in cur.fetchall()]


def _insert_alias(
    conn: psycopg.Connection,
    client_id: str,
    raw_name: str,
    canonical_name: str,
    match_method: str,
    confidence: float | None,
) -> dict[str, Any]:
    query = """
        insert into vendor_aliases (client_id, raw_name, canonical_name, match_method, confidence)
        values (%(client_id)s, %(raw_name)s, %(canonical_name)s, %(match_method)s, %(confidence)s)
        returning *
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            query,
            {
                "client_id": client_id,
                "raw_name": raw_name,
                "canonical_name": canonical_name,
                "match_method": match_method,
                "confidence": confidence,
            },
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def resolve_vendor_alias(conn: psycopg.Connection, client_id: str, raw_name: str) -> dict[str, Any]:
    """Resolve `raw_name` to a canonical vendor entry, creating one if needed.

    Idempotent: if `(client_id, raw_name)` already has an alias row, that
    row is returned unchanged (this function never re-classifies an
    already-resolved name -- deleting the row is how you'd force a
    re-resolve).

    For a new `raw_name`, compares its normalized form against every
    existing canonical name for this client (see
    `bidscraper.normalize.vendor_alias.find_best_match`) and classifies
    the best match:
      - "merge" (>=0.90 similarity): `raw_name` is recorded as an alias
        of that existing canonical name.
      - "review" (0.75-0.90): plausibly the same vendor, but not merged
        automatically -- recorded as its own canonical entry (so nothing
        is silently conflated) with `match_method='review'` and the score
        kept, so these are easy to find and resolve by hand later.
      - "new" (<0.75, or no existing names yet): recorded as a new
        canonical entry using `raw_name` itself as the canonical name.
    """
    existing = _get_existing_alias(conn, client_id, raw_name)
    if existing is not None:
        return existing

    normalized = normalize_vendor_name(raw_name)
    canonical_names = _get_canonical_names(conn, client_id)
    normalized_to_canonical = {normalize_vendor_name(c): c for c in canonical_names}

    best_normalized, score = find_best_match(normalized, list(normalized_to_canonical.keys()))

    if best_normalized is None:
        return _insert_alias(conn, client_id, raw_name, raw_name, match_method="new", confidence=None)

    band = classify_match(score)
    if band == "merge":
        matched_canonical = normalized_to_canonical[best_normalized]
        return _insert_alias(conn, client_id, raw_name, matched_canonical, match_method="fuzzy_merge", confidence=score)
    if band == "review":
        return _insert_alias(conn, client_id, raw_name, raw_name, match_method="review", confidence=score)

    return _insert_alias(conn, client_id, raw_name, raw_name, match_method="new", confidence=score)


def backfill_vendor_aliases(conn: psycopg.Connection, client_id: str) -> dict[str, int]:
    """Resolve every not-yet-aliased confirmed vendor name for `client_id`.

    Reads distinct `awarded_vendor` values from `bid_awards` (restricted
    to `needs_review = false`, so placeholder/unconfirmed vendor strings
    are never turned into canonical entries), processes names not already
    present in `vendor_aliases` in alphabetical order (deterministic, so
    re-running produces the same clustering), and returns counts by
    `match_method`. Safe to run repeatedly -- already-resolved names are
    untouched (see `resolve_vendor_alias`).
    """
    query = """
        select distinct awarded_vendor
        from bid_awards
        where client_id = %(client_id)s
          and awarded_vendor is not null
          and needs_review = false
        order by awarded_vendor
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, {"client_id": client_id})
        raw_names = [row["awarded_vendor"] for row in cur.fetchall()]

    counts = {"processed": 0, "already_resolved": 0, "fuzzy_merge": 0, "review": 0, "new": 0}
    for raw_name in raw_names:
        already = _get_existing_alias(conn, client_id, raw_name)
        if already is not None:
            counts["already_resolved"] += 1
            continue
        row = resolve_vendor_alias(conn, client_id, raw_name)
        counts["processed"] += 1
        counts[row["match_method"]] = counts.get(row["match_method"], 0) + 1

    return counts
