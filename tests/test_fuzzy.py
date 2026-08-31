import pytest

from bidscraper.db.client import (
    FUZZY_MATCH_THRESHOLD,
    REVIEW_THRESHOLD,
    classify_confidence,
    score_match,
)


def test_score_match_identical_pairs_scores_one() -> None:
    score = score_match("Road Resurfacing", "Acme Paving", "Road Resurfacing", "Acme Paving")
    assert score == pytest.approx(1.0)


def test_score_match_unrelated_pairs_scores_low() -> None:
    score = score_match(
        "Annual Road Resurfacing Contract",
        "Acme Paving Co.",
        "Elevator Modernization Project",
        "Zenith Vertical Transport Inc.",
    )
    assert score < REVIEW_THRESHOLD


def test_thresholds_are_ordered() -> None:
    assert 0.0 <= REVIEW_THRESHOLD < FUZZY_MATCH_THRESHOLD <= 1.0


def test_classify_confidence_merge_band() -> None:
    assert classify_confidence(FUZZY_MATCH_THRESHOLD) == "merge"
    assert classify_confidence(1.0) == "merge"


def test_classify_confidence_review_band() -> None:
    assert classify_confidence(REVIEW_THRESHOLD) == "review"
    assert classify_confidence((REVIEW_THRESHOLD + FUZZY_MATCH_THRESHOLD) / 2) == "review"
    # just below the merge threshold should still be "review", not "merge"
    assert classify_confidence(FUZZY_MATCH_THRESHOLD - 0.001) == "review"


def test_classify_confidence_new_band() -> None:
    assert classify_confidence(0.0) == "new"
    assert classify_confidence(REVIEW_THRESHOLD - 0.001) == "new"
