"""R32.0: deterministic weekly universe refresh + history/reason codes."""
from datetime import date

from app.core.universe.weekly_refresh import (
    ADDED,
    INITIAL,
    REMOVED_NOT_IN_MANIFEST,
    REMOVED_OVERRIDE_DISABLED,
    UNCHANGED,
    compute_weekly_universe,
    iso_week_id,
    weekly_refresh_due,
)
from app.core.universe.refresh_history_store import RefreshHistoryStore

AS_OF = date(2026, 6, 21)


def _manifest(symbols, overrides=None, enabled=True):
    return {
        "version": 1,
        "tiers": [{"name": "CORE", "enabled": enabled, "symbols": list(symbols)}],
        "symbol_overrides": overrides or {},
    }


def test_iso_week_id_stable():
    assert iso_week_id(date(2026, 6, 21)) == "2026-W25"


def test_compute_is_deterministic_and_sorted():
    m = _manifest(["msft", "AAPL", "spy", "AAPL"])
    r1 = compute_weekly_universe(m, AS_OF)
    r2 = compute_weekly_universe(m, AS_OF)
    assert r1.symbols == ["AAPL", "MSFT", "SPY"]
    assert r1.to_dict() == r2.to_dict()
    assert r1.reason_codes == [INITIAL]


def test_disabled_override_excluded():
    m = _manifest(["AAPL", "SPY"], overrides={"SPY": {"enabled": False}})
    r = compute_weekly_universe(m, AS_OF)
    assert r.symbols == ["AAPL"]


def test_added_reason_code():
    m = _manifest(["AAPL", "SPY", "QQQ"])
    r = compute_weekly_universe(m, AS_OF, previous_symbols=["AAPL", "SPY"])
    assert r.added == ["QQQ"]
    assert ADDED in r.reason_codes


def test_removed_override_disabled_reason():
    m = _manifest(["AAPL", "SPY"], overrides={"SPY": {"enabled": False}})
    r = compute_weekly_universe(m, AS_OF, previous_symbols=["AAPL", "SPY"])
    assert r.removed == ["SPY"]
    assert REMOVED_OVERRIDE_DISABLED in r.reason_codes


def test_removed_not_in_manifest_reason():
    m = _manifest(["AAPL"])
    r = compute_weekly_universe(m, AS_OF, previous_symbols=["AAPL", "TSLA"])
    assert r.removed == ["TSLA"]
    assert REMOVED_NOT_IN_MANIFEST in r.reason_codes


def test_unchanged_reason():
    m = _manifest(["AAPL", "SPY"])
    r = compute_weekly_universe(m, AS_OF, previous_symbols=["SPY", "AAPL"])
    assert r.reason_codes == [UNCHANGED]


def test_refresh_due_logic():
    assert weekly_refresh_due(None, AS_OF) is True
    assert weekly_refresh_due(date(2026, 6, 14), AS_OF) is True  # prior week
    assert weekly_refresh_due(date(2026, 6, 21), AS_OF) is False  # same day/week


def test_history_store_append_and_read(tmp_path):
    store = RefreshHistoryStore(path=tmp_path / "hist.jsonl")
    m = _manifest(["AAPL", "SPY"])
    r = compute_weekly_universe(m, AS_OF)
    rec = store.append(
        week_id=r.week_id,
        symbols=r.symbols,
        reason_codes=r.reason_codes,
        added=r.added,
        removed=r.removed,
    )
    assert rec["week_id"] == "2026-W25"
    assert rec["count"] == 2
    recent = store.read_recent()
    assert len(recent) == 1
    assert recent[0]["reason_codes"] == [INITIAL]
    assert store.last()["week_id"] == "2026-W25"


def test_history_newest_first(tmp_path):
    store = RefreshHistoryStore(path=tmp_path / "hist.jsonl")
    store.append(week_id="2026-W24", symbols=["AAPL"], reason_codes=[INITIAL])
    store.append(week_id="2026-W25", symbols=["AAPL", "SPY"], reason_codes=[ADDED])
    recent = store.read_recent()
    assert [r["week_id"] for r in recent] == ["2026-W25", "2026-W24"]
