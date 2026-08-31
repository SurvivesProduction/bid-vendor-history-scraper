from datetime import date

from bidscraper.db.client import compute_record_key


def test_compute_record_key_uses_native_id_when_present() -> None:
    key, method = compute_record_key(
        "ABC-123", "Example County", "Road Resurfacing", "Acme Paving", date(2026, 1, 15)
    )
    assert key == "ABC-123"
    assert method == "native_id"


def test_compute_record_key_hashes_when_no_native_id() -> None:
    key, method = compute_record_key(
        None, "Example County", "Road Resurfacing", "Acme Paving", date(2026, 1, 15)
    )
    assert method == "normalized_hash"
    assert len(key) == 64  # sha256 hex digest length


def test_compute_record_key_hash_is_stable_across_whitespace_and_case() -> None:
    key_a, _ = compute_record_key(
        None, "Example  County", "  Road Resurfacing", "acme paving", date(2026, 1, 15)
    )
    key_b, _ = compute_record_key(
        None, "example county", "Road   Resurfacing", "ACME PAVING", date(2026, 1, 15)
    )
    assert key_a == key_b


def test_compute_record_key_hash_differs_for_different_dates() -> None:
    key_a, _ = compute_record_key(
        None, "Example County", "Road Resurfacing", "Acme Paving", date(2026, 1, 15)
    )
    key_b, _ = compute_record_key(
        None, "Example County", "Road Resurfacing", "Acme Paving", date(2026, 2, 1)
    )
    assert key_a != key_b


def test_compute_record_key_hash_differs_for_different_vendor() -> None:
    key_a, _ = compute_record_key(
        None, "Example County", "Road Resurfacing", "Acme Paving", date(2026, 1, 15)
    )
    key_b, _ = compute_record_key(
        None, "Example County", "Road Resurfacing", "Other Vendor", date(2026, 1, 15)
    )
    assert key_a != key_b
