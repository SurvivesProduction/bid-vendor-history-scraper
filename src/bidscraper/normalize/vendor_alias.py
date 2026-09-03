"""Pure logic for vendor-name canonicalization.

The same real-world vendor commonly appears under several spellings
across different source documents -- punctuation ("Corp" vs "Corp."),
abbreviation spacing ("CT" vs "C. T."), suffix variants ("Inc" vs
"Incorporated"), and genuine near-misses ("Electric" vs "Electrical").
Grouping `bid_awards.awarded_vendor` by exact string therefore
undercounts real vendors' true win totals.

This module has no DB/network dependency -- see `bidscraper.db.vendor_aliases`
for the I/O layer that reads/writes the `vendor_aliases` table using the
functions here. Mirrors the existing bid-record dedup pattern in
`bidscraper.db.client` (`score_match`/`classify_confidence`): pure scoring
and banding functions factored out so they're unit-testable without a
live database.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

MERGE_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.75

_PUNCTUATION_RE = re.compile(r"[.,]")
_WHITESPACE_RE = re.compile(r"\s+")
# Collapses spaced-out single-letter abbreviations ("c t" -> "ct") so
# "C. T. Electrical Corp" and "CT Electrical Corp" normalize to the same
# form before fuzzy scoring -- without this, the two land in different
# similarity bands purely because of formatting, not identity.
_SPACED_ABBREVIATION_RE = re.compile(r"\b(?:[a-z] )+[a-z]\b")


def normalize_vendor_name(raw_name: str) -> str:
    """Deterministic cleanup applied before fuzzy comparison.

    Lowercases, strips periods/commas, collapses whitespace, and joins
    spaced-out single-letter abbreviations. This does NOT resolve real
    spelling differences (e.g. "Electric" vs "Electrical") -- that's what
    `score_similarity` is for. This step only removes formatting noise
    that isn't a genuine identity signal.
    """
    text = raw_name.strip().lower()
    text = _PUNCTUATION_RE.sub("", text)
    text = _SPACED_ABBREVIATION_RE.sub(lambda m: m.group(0).replace(" ", ""), text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def score_similarity(name_a: str, name_b: str) -> float:
    """Similarity between two vendor names, 0-1 scale.

    Both inputs should already be normalized via `normalize_vendor_name`.
    Uses `rapidfuzz.fuzz.token_sort_ratio` (0-100), normalized to 0-1, the
    same scoring function the bid-record dedup logic uses.
    """
    return fuzz.token_sort_ratio(name_a, name_b) / 100.0


def classify_match(confidence: float) -> str:
    """Classify a vendor-name similarity score into a decision band.

    Returns one of:
      - "merge": confidence >= MERGE_THRESHOLD -- treat as the same vendor.
      - "review": REVIEW_THRESHOLD <= confidence < MERGE_THRESHOLD -- plausibly
        the same vendor, but not confident enough to merge automatically.
      - "new": confidence < REVIEW_THRESHOLD -- treat as a distinct vendor.

    Same threshold values and rationale as `bidscraper.db.client`'s
    `classify_confidence`: a single cutoff forces a choice between merging
    too aggressively (conflating two distinct vendors) or too
    conservatively (never catching real spelling variants); splitting out
    a review band turns that ambiguity into something a human can resolve
    instead of a silent guess in either direction.
    """
    if confidence >= MERGE_THRESHOLD:
        return "merge"
    if confidence >= REVIEW_THRESHOLD:
        return "review"
    return "new"


def find_best_match(
    normalized_name: str, existing_canonical_names: list[str]
) -> tuple[str | None, float]:
    """Find the best-scoring existing canonical name for `normalized_name`.

    `existing_canonical_names` should already be normalized (callers
    typically pass the distinct `canonical_name` values already recorded
    for a client). Returns `(None, 0.0)` if the list is empty.
    """
    best_name: str | None = None
    best_score = 0.0
    for candidate in existing_canonical_names:
        score = score_similarity(normalized_name, candidate)
        if score > best_score:
            best_score = score
            best_name = candidate
    return best_name, best_score
