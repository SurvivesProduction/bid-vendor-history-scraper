import pytest

from bidscraper.normalize.vendor_alias import (
    MERGE_THRESHOLD,
    REVIEW_THRESHOLD,
    classify_match,
    find_best_match,
    normalize_vendor_name,
    score_similarity,
)


def test_normalize_strips_punctuation_and_case() -> None:
    assert normalize_vendor_name("CT Electric Corp.") == "ct electric corp"
    assert normalize_vendor_name("Baltimore Contractors, Inc.") == "baltimore contractors inc"


def test_normalize_collapses_spaced_abbreviations() -> None:
    assert normalize_vendor_name("C. T. Electrical Corp") == normalize_vendor_name("CT Electrical Corp")


def test_normalize_collapses_whitespace() -> None:
    assert normalize_vendor_name("  A & S   Unlimited  ") == "a & s unlimited"


def test_score_similarity_real_variants_score_high() -> None:
    # These four strings are all the same real-world vendor, observed
    # verbatim across different AACPS Bid Results documents.
    variants = [
        "CT Electric Corp",
        "CT Electric Corp.",
        "CT Electrical Corp",
        "C. T. Electrical Corp",
    ]
    normalized = [normalize_vendor_name(v) for v in variants]
    for i in range(len(normalized)):
        for j in range(i + 1, len(normalized)):
            score = score_similarity(normalized[i], normalized[j])
            assert score >= MERGE_THRESHOLD, f"{variants[i]!r} vs {variants[j]!r} scored {score}"


def test_score_similarity_distinct_vendors_score_low() -> None:
    pairs = [
        ("CT Electrical Corp", "BoMark Electric"),
        ("CT Electrical Corp", "Grounded Electrical Construction"),
    ]
    for a, b in pairs:
        score = score_similarity(normalize_vendor_name(a), normalize_vendor_name(b))
        assert score < REVIEW_THRESHOLD, f"{a!r} vs {b!r} scored {score}, expected a clear non-match"


def test_thresholds_are_ordered() -> None:
    assert 0.0 <= REVIEW_THRESHOLD < MERGE_THRESHOLD <= 1.0


def test_classify_match_bands() -> None:
    assert classify_match(MERGE_THRESHOLD) == "merge"
    assert classify_match(1.0) == "merge"
    assert classify_match(REVIEW_THRESHOLD) == "review"
    assert classify_match(MERGE_THRESHOLD - 0.001) == "review"
    assert classify_match(0.0) == "new"
    assert classify_match(REVIEW_THRESHOLD - 0.001) == "new"


def test_find_best_match_picks_highest_scoring_candidate() -> None:
    candidates = ["bomark electric", "ct electrical corp", "grounded electrical construction"]
    best, score = find_best_match("ct electric corp", candidates)
    assert best == "ct electrical corp"
    assert score == pytest.approx(score_similarity("ct electric corp", "ct electrical corp"))


def test_find_best_match_empty_candidates() -> None:
    best, score = find_best_match("anything", [])
    assert best is None
    assert score == 0.0
