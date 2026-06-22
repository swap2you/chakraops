# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — refresh journal and history integrity (final operational pass)."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.universe import refresh_lock
from app.core.universe.refresh_history_store import (
    RefreshHistoryCorruptionError,
    RefreshHistoryError,
    RefreshHistoryStore,
)
from app.core.universe.weekly_refresh import WeeklyRefreshCriticalError, recover_pending_transaction

AS_OF = date(2026, 6, 22)
WEEK = "2026-W26"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    refresh_lock.clear_journal("weekly_refresh")
    return tmp_path


def test_malformed_journal_json_fails_loud(env) -> None:
    path = refresh_lock.journal_path("weekly_refresh")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(refresh_lock.RefreshJournalError, match="malformed"):
        refresh_lock.read_journal("weekly_refresh")


def test_unreadable_journal_fails_loud(env, monkeypatch) -> None:
    path = refresh_lock.journal_path("weekly_refresh")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")

    def _boom(_self):
        raise OSError("permission denied")

    monkeypatch.setattr(refresh_lock.Path, "read_text", _boom, raising=False)
    with pytest.raises(refresh_lock.RefreshJournalError, match="unreadable"):
        refresh_lock.read_journal("weekly_refresh")


def test_incomplete_journal_structure_fails_loud(env) -> None:
    refresh_lock.atomic_write_json(
        refresh_lock.journal_path("weekly_refresh"),
        {"week_id": WEEK},
    )
    with pytest.raises(refresh_lock.RefreshJournalError, match="missing required"):
        refresh_lock.read_journal("weekly_refresh")


def test_journal_clear_failure_raises(env, monkeypatch) -> None:
    path = refresh_lock.journal_path("weekly_refresh")
    refresh_lock.write_journal(
        "weekly_refresh",
        {
            "week_id": WEEK,
            "phase": "apply",
            "prev_overlay": {"added": [], "removed": []},
        },
    )

    def _fail_unlink(_self):
        raise OSError("clear failed")

    monkeypatch.setattr(refresh_lock.Path, "unlink", _fail_unlink, raising=False)
    with pytest.raises(refresh_lock.RefreshJournalError, match="failed to clear"):
        refresh_lock.clear_journal("weekly_refresh")
    assert path.exists()


def test_recovery_reports_critical_when_journal_remains(env, monkeypatch) -> None:
    store = RefreshHistoryStore(path=env / "history.jsonl")
    refresh_lock.write_journal(
        "weekly_refresh",
        {
            "week_id": WEEK,
            "phase": "history",
            "prev_overlay": {"added": [], "removed": []},
        },
    )

    def _noop_clear(_name: str) -> None:
        return None

    monkeypatch.setattr(refresh_lock, "clear_journal", _noop_clear)
    with pytest.raises(WeeklyRefreshCriticalError, match="journal remained"):
        recover_pending_transaction(history_store=store)


def test_unreadable_history_not_treated_as_empty(env, monkeypatch) -> None:
    store = RefreshHistoryStore(path=env / "history.jsonl")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text('{"week_id":"2026-W01","symbols":["SPY"]}\n', encoding="utf-8")

    monkeypatch.setattr(
        RefreshHistoryStore,
        "_read_existing_strict",
        lambda _self: (_ for _ in ()).throw(RefreshHistoryError("read blocked")),
    )
    with pytest.raises(RefreshHistoryError, match="read blocked"):
        store.last()


def test_malformed_history_line_fails_loud(env) -> None:
    store = RefreshHistoryStore(path=env / "history.jsonl")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    original = '{"week_id":"2026-W01","symbols":["SPY"]}\n{bad\n'
    store.path.write_text(original, encoding="utf-8")
    with pytest.raises(RefreshHistoryCorruptionError, match="malformed"):
        store.read_all_strict()
    assert store.path.read_text(encoding="utf-8") == original


def test_history_read_failure_prevents_append_overwrite(env, monkeypatch) -> None:
    store = RefreshHistoryStore(path=env / "history.jsonl")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    original = '{"week_id":"2026-W01","symbols":["SPY"],"count":1,"added":[],"removed":[],"reason_codes":[]}\n'
    store.path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(
        RefreshHistoryStore,
        "_read_existing_strict",
        lambda _self: (_ for _ in ()).throw(RefreshHistoryError("read blocked")),
    )
    with pytest.raises(RefreshHistoryError):
        store.append(
            week_id=WEEK,
            symbols=["AAPL"],
            reason_codes=["ADDED"],
        )
    assert store.path.read_text(encoding="utf-8") == original


def test_malformed_history_preserves_file_on_append(env) -> None:
    store = RefreshHistoryStore(path=env / "history.jsonl")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    original = "not-json-line\n"
    store.path.write_text(original, encoding="utf-8")
    with pytest.raises(RefreshHistoryCorruptionError):
        store.append(
            week_id=WEEK,
            symbols=["AAPL"],
            reason_codes=["ADDED"],
        )
    assert store.path.read_text(encoding="utf-8") == original
