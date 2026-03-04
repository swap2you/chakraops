# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.5: Backtest run persistence. SQLite + files under data/reports/backtests/. No FAIL_/WARN_."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.backtest.backtest_runner_r275 import BacktestResult, run_backtest

import logging
logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_OVERRIDE_DB: Optional[Path] = None
_OVERRIDE_BASE: Optional[Path] = None


def _data_dir() -> Path:
    """Base data dir. R26.7: DATA_DIR env override."""
    if _OVERRIDE_BASE is not None:
        return _OVERRIDE_BASE
    data_dir_env = os.environ.get("DATA_DIR")
    if data_dir_env:
        return Path(data_dir_env).resolve()
    base = Path(__file__).resolve().parents[3]
    return base / "data"


def _db_path() -> Path:
    """Backtest runs DB."""
    d = _data_dir()
    d.mkdir(parents=True, exist_ok=True)
    if _OVERRIDE_DB is not None:
        return _OVERRIDE_DB
    return d / "backtest.db"


def _backtests_base() -> Path:
    """data/reports/backtests/"""
    return _data_dir() / "reports" / "backtests"


def set_backtest_db_path(path: Optional[Path]) -> None:
    global _OVERRIDE_DB
    _OVERRIDE_DB = Path(path).resolve() if path else None


def set_backtest_base_path(path: Optional[Path]) -> None:
    global _OVERRIDE_BASE
    _OVERRIDE_BASE = Path(path).resolve() if path else None


def init_backtest_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS backtest_runs (
        id TEXT PRIMARY KEY,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        mode TEXT NOT NULL,
        created_ts TEXT NOT NULL,
        path_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_backtest_created ON backtest_runs(created_ts DESC);
    """
    with _LOCK:
        conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        try:
            conn.executescript(sql)
            conn.commit()
        finally:
            conn.close()


def _run_dir(start_date: str, end_date: str, mode: str) -> Path:
    """YYYY-MM-DD_to_YYYY-MM-DD/live|paper|mixed/run_<timestamp>/"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    segment = f"{start_date}_to_{end_date}"
    base = _backtests_base() / segment / mode / f"run_{ts}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _summary_dict(result: BacktestResult, start_date: str, end_date: str) -> Dict[str, Any]:
    """Safe for JSON; no FAIL_/WARN_."""
    return {
        "start_date": start_date,
        "end_date": end_date,
        "mode": result.mode,
        "total_realized_pl": result.total_realized_pl,
        "total_fees": result.total_fees,
        "trade_count": result.trade_count,
        "win_count": result.win_count,
        "loss_count": result.loss_count,
        "win_rate": result.win_rate,
        "by_strategy": result.by_strategy,
        "max_drawdown_proxy": result.max_drawdown_proxy,
    }


def run_and_persist(
    start_date: str,
    end_date: str,
    include_paper: bool = False,
    paper_only: bool = False,
) -> Dict[str, Any]:
    """
    Run backtest and persist to data/reports/backtests/... and SQLite.
    Returns { run_id, created_ts, mode, paths: { summary_json, trades_csv }, metrics }.
    """
    start_date = start_date.strip()[:10]
    end_date = end_date.strip()[:10]
    result = run_backtest(start_date, end_date, include_paper=include_paper, paper_only=paper_only)
    mode = result.mode
    run_dir = _run_dir(start_date, end_date, mode)
    run_id = str(uuid.uuid4())
    created_ts = datetime.now(timezone.utc).isoformat()

    summary_path = run_dir / "backtest_summary.json"
    trades_path = run_dir / "backtest_trades.csv"
    summary_data = _summary_dict(result, start_date, end_date)
    summary_data["run_id"] = run_id
    summary_data["created_ts"] = created_ts
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    with open(trades_path, "w", encoding="utf-8", newline="") as f:
        if result.trades:
            w = csv.DictWriter(f, fieldnames=list(result.trades[0].keys()), extrasaction="ignore")
            w.writeheader()
            w.writerows(result.trades)

    path_json = json.dumps({
        "summary_json": str(summary_path),
        "trades_csv": str(trades_path),
        "run_dir": str(run_dir),
    })
    init_backtest_db()
    with _LOCK:
        conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        try:
            conn.execute(
                "INSERT INTO backtest_runs (id, start_date, end_date, mode, created_ts, path_json) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, start_date, end_date, mode, created_ts, path_json),
            )
            conn.commit()
        finally:
            conn.close()

    return {
        "run_id": run_id,
        "created_ts": created_ts,
        "mode": mode,
        "paths": {"summary_json": str(summary_path), "trades_csv": str(trades_path)},
        "metrics": summary_data,
        "trades": result.trades,
    }


def list_runs(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """List backtest runs (created_ts desc)."""
    init_backtest_db()
    with _LOCK:
        conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, start_date, end_date, mode, created_ts, path_json FROM backtest_runs ORDER BY created_ts DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Get one run by id."""
    init_backtest_db()
    with _LOCK:
        conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT id, start_date, end_date, mode, created_ts, path_json FROM backtest_runs WHERE id = ?", (run_id.strip(),)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
