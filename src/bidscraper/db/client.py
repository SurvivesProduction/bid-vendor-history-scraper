"""Generic Postgres client wrapper for bidscraper.

Handles connecting to Postgres via standard environment variables, the
record-key/dedup-method computation, fuzzy-match lookups, and the 3-tier
upsert logic shared by every scraper. Nothing in this module is specific
to any hosting provider (e.g. Supabase) or client -- that kind of wiring
belongs in a downstream "full" deployment package.

3-tier dedup strategy used by `upsert_bid_award`:

1. Exact match on (client_id, source, record_key). record_key is either
   the source's native record id (dedup_method='native_id') or a sha256
   hash of the normalized agency+title+vendor+date (dedup_method=
   'normalized_hash'), computed by `compute_record_key`. If a row with
   this exact key already exists, its content is refreshed in place.
2. If the record_key is new, `find_fuzzy_match` looks for a similar
   existing row (same client_id/source/awarding_agency, award_date within
   a small window, high title+vendor similarity):
     - confidence >= FUZZY_MATCH_THRESHOLD: treated as the same record
       under a different key -- merge into the matched row instead of
       inserting a duplicate.
     - REVIEW_THRESHOLD <= confidence < FUZZY_MATCH_THRESHOLD: inserted
       as a new row but flagged `needs_review` for a human to confirm.
     - confidence < REVIEW_THRESHOLD (or no candidate rows): inserted as
       a genuinely new row.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from rapidfuzz import fuzz

from bidscraper.config import DatabaseConfig
from bidscraper.normalize.schema import BidAward

FUZZY_MATCH_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.75


def get_connection(dsn: str | None = None) -> psycopg.Connection:
    """Open a Postgres connection.

    Uses `dsn` if given, otherwise resolves connection settings from the
    environment via `DatabaseConfig.from_env()`.
    """
    resolved_dsn = dsn or DatabaseConfig.from_env().dsn
    return psycopg.connect(resolved_dsn)


def _normalize_text(value: str) -> str:
    """Lowercase and collapse whitespace for hash-based dedup comparisons."""
    return re.sub(r"\s+", " ", value.strip().lower())


def compute_record_key(
    source_record_id: str | None,
    awarding_agency: str,
    project_title: str,
    awarded_vendor: str,
    award_date: date | None,
) -> tuple[str, str]:
    """Compute (record_key, dedup_method) for a bid award.

    If a native `source_record_id` is available, it is used directly as
    the record key with dedup_method='native_id'. Otherwise a stable
    sha256 hash of the normalized agency + title + vendor + date is used,
    with dedup_method='normalized_hash'.
    """
    if source_record_id:
        return source_record_id, "native_id"

    date_part = award_date.isoformat() if award_date else ""
    normalized = "|".join(
        _normalize_text(part)
        for part in (awarding_agency, project_title, awarded_vendor, date_part)
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest, "normalized_hash"


def score_match(title_a: str, vendor_a: str, title_b: str, vendor_b: str) -> float:
    """Pure similarity score between two (title, vendor) pairs, 0-1 scale.

    Averages `rapidfuzz.fuzz.token_sort_ratio` (0-100) across title and
    vendor, then normalizes to a 0-1 confidence score. Factored out of
    `find_fuzzy_match` so it's unit-testable without a live database.
    """
    title_score = fuzz.token_sort_ratio(title_a, title_b)
    vendor_score = fuzz.token_sort_ratio(vendor_a, vendor_b)
    return ((title_score + vendor_score) / 2) / 100.0


def classify_confidence(confidence: float) -> str:
    """Classify a fuzzy-match confidence score into a dedup band.

    Returns one of:
      - "merge": confidence >= FUZZY_MATCH_THRESHOLD
      - "review": REVIEW_THRESHOLD <= confidence < FUZZY_MATCH_THRESHOLD
      - "new": confidence < REVIEW_THRESHOLD
    """
    if confidence >= FUZZY_MATCH_THRESHOLD:
        return "merge"
    if confidence >= REVIEW_THRESHOLD:
        return "review"
    return "new"


def find_fuzzy_match(
    conn: psycopg.Connection,
    client_id: str,
    source: str,
    awarding_agency: str,
    award_date: date | None,
    project_title: str,
    awarded_vendor: str,
    window_days: int = 3,
) -> tuple[dict[str, Any] | None, float]:
    """Find the best fuzzy-matching existing row, if any.

    Looks at existing rows for the same client_id + source + awarding_agency
    with award_date within `window_days` of the given `award_date`, and
    scores each candidate with `score_match`. Returns (best_row, confidence),
    or (None, 0.0) if there are no candidates (including when award_date
    is None, since there's no window to search).
    """
    if award_date is None:
        return None, 0.0

    start = award_date - timedelta(days=window_days)
    end = award_date + timedelta(days=window_days)

    query = """
        select *
        from bid_awards
        where client_id = %(client_id)s
          and source = %(source)s
          and awarding_agency = %(awarding_agency)s
          and award_date between %(start)s and %(end)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            query,
            {
                "client_id": client_id,
                "source": source,
                "awarding_agency": awarding_agency,
                "start": start,
                "end": end,
            },
        )
        candidates = cur.fetchall()

    best_row: dict[str, Any] | None = None
    best_score = 0.0
    for row in candidates:
        score = score_match(
            project_title,
            awarded_vendor,
            row.get("project_title") or "",
            row.get("awarded_vendor") or "",
        )
        if score > best_score:
            best_score = score
            best_row = row

    if best_row is None:
        return None, 0.0
    return best_row, best_score


def upsert_bid_award(conn: psycopg.Connection, bid: BidAward) -> dict[str, Any]:
    """Insert or update a bid award using the 3-tier dedup strategy.

    See the module docstring for the full description of the strategy.
    Always bumps last_seen_at on update; first_seen_at is only ever set
    (via the column default) on insert. Returns the resulting row.
    """
    record_key, dedup_method = compute_record_key(
        bid.source_record_id,
        bid.awarding_agency,
        bid.project_title,
        bid.awarded_vendor,
        bid.award_date,
    )

    existing = _find_by_exact_key(conn, bid.client_id, bid.source, record_key)
    if existing is not None:
        row = _update_row_content(conn, existing["id"], bid)
        conn.commit()
        return row

    match_row, confidence = find_fuzzy_match(
        conn,
        bid.client_id,
        bid.source,
        bid.awarding_agency,
        bid.award_date,
        bid.project_title,
        bid.awarded_vendor,
    )

    if match_row is not None:
        band = classify_confidence(confidence)
        if band == "merge":
            row = _merge_row(conn, match_row["id"], bid, confidence)
            conn.commit()
            return row
        if band == "review":
            row = _insert_row(conn, bid, record_key, dedup_method, confidence, needs_review=True)
            conn.commit()
            return row

    row = _insert_row(conn, bid, record_key, dedup_method, None, needs_review=False)
    conn.commit()
    return row


def _find_by_exact_key(
    conn: psycopg.Connection, client_id: str, source: str, record_key: str
) -> dict[str, Any] | None:
    query = """
        select *
        from bid_awards
        where client_id = %(client_id)s
          and source = %(source)s
          and record_key = %(record_key)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, {"client_id": client_id, "source": source, "record_key": record_key})
        return cur.fetchone()


def _content_params(bid: BidAward) -> dict[str, Any]:
    return {
        "source_record_id": bid.source_record_id,
        "awarding_agency": bid.awarding_agency,
        "project_title": bid.project_title,
        "project_description": bid.project_description,
        "awarded_vendor": bid.awarded_vendor,
        "award_date": bid.award_date,
        "contract_value": bid.contract_value,
        "contract_term_end": bid.contract_term_end,
        "raw_data": Jsonb(bid.raw_data),
    }


def _insert_row(
    conn: psycopg.Connection,
    bid: BidAward,
    record_key: str,
    dedup_method: str,
    match_confidence: float | None,
    needs_review: bool,
) -> dict[str, Any]:
    query = """
        insert into bid_awards (
            client_id, source, source_record_id, record_key, dedup_method,
            match_confidence, needs_review, awarding_agency, project_title,
            project_description, awarded_vendor, award_date, contract_value,
            contract_term_end, raw_data
        ) values (
            %(client_id)s, %(source)s, %(source_record_id)s, %(record_key)s, %(dedup_method)s,
            %(match_confidence)s, %(needs_review)s, %(awarding_agency)s, %(project_title)s,
            %(project_description)s, %(awarded_vendor)s, %(award_date)s, %(contract_value)s,
            %(contract_term_end)s, %(raw_data)s
        )
        returning *
    """
    params = {
        "client_id": bid.client_id,
        "source": bid.source,
        "record_key": record_key,
        "dedup_method": dedup_method,
        "match_confidence": match_confidence,
        "needs_review": needs_review,
        **_content_params(bid),
    }
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    assert row is not None
    return row


def _update_row_content(conn: psycopg.Connection, row_id: Any, bid: BidAward) -> dict[str, Any]:
    """Refresh an existing row's content on an exact record_key match.

    Deliberately leaves dedup_method/match_confidence/needs_review alone --
    those describe how the row originally acquired its identity, not this
    re-scrape of already-identified content.
    """
    query = """
        update bid_awards
        set source_record_id = %(source_record_id)s,
            awarding_agency = %(awarding_agency)s,
            project_title = %(project_title)s,
            project_description = %(project_description)s,
            awarded_vendor = %(awarded_vendor)s,
            award_date = %(award_date)s,
            contract_value = %(contract_value)s,
            contract_term_end = %(contract_term_end)s,
            raw_data = %(raw_data)s,
            last_seen_at = now(),
            updated_at = now()
        where id = %(id)s
        returning *
    """
    params = {"id": row_id, **_content_params(bid)}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    assert row is not None
    return row


def _merge_row(
    conn: psycopg.Connection, row_id: Any, bid: BidAward, confidence: float
) -> dict[str, Any]:
    """Merge an incoming record into a fuzzy-matched existing row."""
    query = """
        update bid_awards
        set source_record_id = %(source_record_id)s,
            dedup_method = 'fuzzy_merge',
            match_confidence = %(match_confidence)s,
            needs_review = false,
            awarding_agency = %(awarding_agency)s,
            project_title = %(project_title)s,
            project_description = %(project_description)s,
            awarded_vendor = %(awarded_vendor)s,
            award_date = %(award_date)s,
            contract_value = %(contract_value)s,
            contract_term_end = %(contract_term_end)s,
            raw_data = %(raw_data)s,
            last_seen_at = now(),
            updated_at = now()
        where id = %(id)s
        returning *
    """
    params = {"id": row_id, "match_confidence": confidence, **_content_params(bid)}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    assert row is not None
    return row
