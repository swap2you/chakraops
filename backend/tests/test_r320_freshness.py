"""R32.0: freshness timestamps + stale-data blocking gate."""
from datetime import datetime, timedelta, timezone

from app.core.data_reliability.freshness import (
    FRESH,
    MISSING,
    STALE,
    evaluate_freshness,
    stale_data_gate,
)

NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def test_fresh_within_max_age():
    r = evaluate_freshness("CHAIN", NOW - timedelta(seconds=30), max_age_seconds=60, now=NOW)
    assert r.status == FRESH
    assert r.is_blocking is False
    assert r.as_of_utc is not None
    assert r.age_seconds == 30


def test_stale_beyond_max_age_blocks_when_required():
    r = evaluate_freshness("CHAIN", NOW - timedelta(seconds=120), max_age_seconds=60, now=NOW)
    assert r.status == STALE
    assert r.is_blocking is True


def test_stale_does_not_block_when_optional():
    r = evaluate_freshness(
        "MACRO", NOW - timedelta(seconds=999), max_age_seconds=60, now=NOW, required=False
    )
    assert r.status == STALE
    assert r.is_blocking is False


def test_missing_data_is_blocking_when_required():
    r = evaluate_freshness("QUOTE", None, max_age_seconds=60, now=NOW)
    assert r.status == MISSING
    assert r.as_of_utc is None
    assert r.is_blocking is True


def test_naive_timestamp_treated_as_utc():
    naive = datetime(2026, 6, 21, 11, 59, 30)
    r = evaluate_freshness("CHAIN", naive, max_age_seconds=60, now=NOW)
    assert r.status == FRESH


def test_invalid_max_age_raises():
    try:
        evaluate_freshness("X", NOW, max_age_seconds=0, now=NOW)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_gate_blocks_with_sorted_reason_codes():
    results = [
        evaluate_freshness("OPTIONS_CHAIN", NOW - timedelta(seconds=999), max_age_seconds=60, now=NOW),
        evaluate_freshness("EQUITY_QUOTE", None, max_age_seconds=60, now=NOW),
        evaluate_freshness("IV_RANK", NOW - timedelta(seconds=5), max_age_seconds=60, now=NOW),
    ]
    gate = stale_data_gate(results)
    assert gate.blocked is True
    assert gate.reason_codes == ["MISSING_EQUITY_QUOTE", "STALE_OPTIONS_CHAIN"]


def test_gate_allows_when_all_fresh():
    results = [
        evaluate_freshness("OPTIONS_CHAIN", NOW, max_age_seconds=60, now=NOW),
        evaluate_freshness("EQUITY_QUOTE", NOW, max_age_seconds=60, now=NOW),
    ]
    gate = stale_data_gate(results)
    assert gate.blocked is False
    assert gate.reason_codes == []


def test_gate_to_dict_shape():
    gate = stale_data_gate([evaluate_freshness("X", None, max_age_seconds=60, now=NOW)])
    d = gate.to_dict()
    assert d["blocked"] is True
    assert d["reason_codes"] == ["MISSING_X"]
    assert d["inputs"][0]["label"] == "X"
