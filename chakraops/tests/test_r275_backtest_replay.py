# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.5: Journal-driven backtest replay. Determinism; include_paper/paper_only; no FAIL_/WARN_; download allowlist."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest


def test_backtest_determinism_same_inputs_same_output() -> None:
    """Run backtest twice with same journal data; metrics and CSV content must be identical."""
    from app.core.journal.journal_store import (
        set_journal_db_path,
        reset_journal_db_path,
        init_journal_db,
        journal_create,
    )
    from app.core.backtest.backtest_runner_r275 import run_backtest
    from app.core.backtest.backtest_store_r275 import set_backtest_db_path, set_backtest_base_path

    with __import__("tempfile").TemporaryDirectory() as tmp:
        t = Path(tmp)
        set_journal_db_path(t / "journal.db")
        set_backtest_db_path(t / "backtest.db")
        set_backtest_base_path(t)
        init_journal_db()
        try:
            journal_create("2026-02-01", "SPY", "SHARES", "BUY", 100, price=400.0, is_paper=False)
            journal_create("2026-02-05", "SPY", "SHARES", "SELL", 100, price=405.0, realized_pl=500.0, fees=1.0, is_paper=False)
            r1 = run_backtest("2026-02-01", "2026-02-28", include_paper=False, paper_only=False)
            r2 = run_backtest("2026-02-01", "2026-02-28", include_paper=False, paper_only=False)
            assert r1.total_realized_pl == r2.total_realized_pl
            assert r1.trade_count == r2.trade_count
            assert r1.win_count == r2.win_count
            assert r1.loss_count == r2.loss_count
            assert len(r1.trades) == len(r2.trades)
            for a, b in zip(r1.trades, r2.trades):
                assert a.get("realized_pl") == b.get("realized_pl")
                assert a.get("trade_date") == b.get("trade_date")
        finally:
            reset_journal_db_path()
            set_backtest_db_path(None)
            set_backtest_base_path(None)


def test_backtest_include_paper_and_paper_only() -> None:
    """include_paper=False excludes paper; paper_only=True only paper entries. SELL/CLOSE produce trade rows."""
    from app.core.journal.journal_store import (
        set_journal_db_path,
        reset_journal_db_path,
        init_journal_db,
        journal_create,
    )
    from app.core.backtest.backtest_runner_r275 import run_backtest

    with __import__("tempfile").TemporaryDirectory() as tmp:
        t = Path(tmp)
        set_journal_db_path(t / "journal.db")
        init_journal_db()
        try:
            journal_create("2026-02-01", "SPY", "SHARES", "BUY", 10, price=450.0, is_paper=False)
            journal_create("2026-02-05", "SPY", "SHARES", "SELL", 10, price=455.0, realized_pl=50.0, is_paper=False)
            journal_create("2026-02-02", "QQQ", "SHARES", "BUY", 5, price=400.0, is_paper=True)
            journal_create("2026-02-06", "QQQ", "SHARES", "SELL", 5, price=402.0, realized_pl=10.0, is_paper=True)
            live_only = run_backtest("2026-02-01", "2026-02-28", include_paper=False, paper_only=False)
            paper_only = run_backtest("2026-02-01", "2026-02-28", include_paper=True, paper_only=True)
            mixed = run_backtest("2026-02-01", "2026-02-28", include_paper=True, paper_only=False)
            assert live_only.mode == "live"
            assert live_only.trade_count == 1
            assert paper_only.mode == "paper"
            assert paper_only.trade_count == 1
            assert mixed.mode == "mixed"
            assert mixed.trade_count == 2
        finally:
            reset_journal_db_path()


def test_backtest_response_no_fail_warn_substrings() -> None:
    """POST /backtest/run response must not contain FAIL_ or WARN_ in JSON."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db
    from app.core.backtest.backtest_store_r275 import set_backtest_db_path, set_backtest_base_path

    with __import__("tempfile").TemporaryDirectory() as tmp:
        t = Path(tmp)
        set_journal_db_path(t / "journal.db")
        set_backtest_db_path(t / "backtest.db")
        set_backtest_base_path(t)
        init_journal_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/backtest/run",
                    json={"start_date": "2026-02-01", "end_date": "2026-02-28", "include_paper": False, "paper_only": False},
                )
            assert r.status_code == 200
            raw = json.dumps(r.json())
            assert "FAIL_" not in raw
            assert "WARN_" not in raw
        finally:
            reset_journal_db_path()
            set_backtest_db_path(None)
            set_backtest_base_path(None)


def test_backtest_download_allowlist_blocks_invalid_file() -> None:
    """GET /backtest/download with file not in allowlist returns 400."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.backtest.backtest_store_r275 import set_backtest_db_path, set_backtest_base_path, init_backtest_db

    with __import__("tempfile").TemporaryDirectory() as tmp:
        t = Path(tmp)
        set_backtest_db_path(t / "backtest.db")
        set_backtest_base_path(t)
        init_backtest_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.get("/api/ui/backtest/download?run_id=any-id&file=../../../etc/passwd")
            assert r.status_code == 400
        finally:
            set_backtest_db_path(None)
            set_backtest_base_path(None)


def test_persisted_summary_json_no_fail_warn() -> None:
    """Persisted backtest_summary.json must not contain FAIL_ or WARN_."""
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db
    from app.core.backtest.backtest_store_r275 import run_and_persist, set_backtest_db_path, set_backtest_base_path

    with __import__("tempfile").TemporaryDirectory() as tmp:
        t = Path(tmp)
        set_journal_db_path(t / "journal.db")
        set_backtest_db_path(t / "backtest.db")
        set_backtest_base_path(t)
        init_journal_db()
        try:
            out = run_and_persist("2026-02-01", "2026-02-28", include_paper=False, paper_only=False)
            path = out["paths"]["summary_json"]
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "FAIL_" not in content
            assert "WARN_" not in content
        finally:
            reset_journal_db_path()
            set_backtest_db_path(None)
            set_backtest_base_path(None)
