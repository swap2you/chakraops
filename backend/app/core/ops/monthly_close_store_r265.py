# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.5: Monthly close pack — state table + generator. data/reports/<YYYY-MM>/; no FAIL_/WARN_."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import sqlite3
import threading
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_OVERRIDE_BASE_PATH: Optional[Path] = None

ALLOWED_FILES = frozenset({"monthly_report.json", "monthly_report.csv", "journal_export.csv", "summary.txt"})


def _reports_base_path() -> Path:
    """Base for data/reports/ (not out/). R26.7: DATA_DIR env override."""
    if _OVERRIDE_BASE_PATH is not None:
        return _OVERRIDE_BASE_PATH
    data_dir_env = os.environ.get("DATA_DIR")
    if data_dir_env:
        return Path(data_dir_env).resolve() / "reports"
    base = Path(__file__).resolve().parents[3]
    return base / "data" / "reports"


def _state_db_path() -> Path:
    """SQLite for monthly_close_state under data/. R26.7: DATA_DIR env override."""
    data_dir_env = os.environ.get("DATA_DIR")
    if data_dir_env:
        data_dir = Path(data_dir_env).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "monthly_close_r265.db"
    base = Path(__file__).resolve().parents[3]
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "monthly_close_r265.db"


def set_reports_base_path(path: Optional[Path]) -> None:
    """Override reports base path (for tests). None = reset."""
    global _OVERRIDE_BASE_PATH
    _OVERRIDE_BASE_PATH = Path(path).resolve() if path else None


def reset_reports_base_path() -> None:
    """Reset to default reports base path."""
    global _OVERRIDE_BASE_PATH
    _OVERRIDE_BASE_PATH = None


def _get_conn() -> sqlite3.Connection:
    path = _state_db_path()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


PACK_LIVE = "live"
PACK_PAPER = "paper"


def _norm_pack(pack: Optional[str]) -> str:
    p = (pack or "").strip().lower()
    return PACK_PAPER if p == PACK_PAPER else PACK_LIVE


def init_monthly_close_db() -> None:
    """Create monthly_close_state table if not exist. R27.1: monthly_close_pack for live/paper subdirs."""
    sql = """
    CREATE TABLE IF NOT EXISTS monthly_close_state (
        month TEXT PRIMARY KEY,
        generated_ts TEXT NOT NULL,
        paths_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS monthly_close_pack (
        month TEXT NOT NULL,
        pack TEXT NOT NULL,
        generated_ts TEXT NOT NULL,
        paths_json TEXT NOT NULL,
        PRIMARY KEY (month, pack)
    );
    """
    with _LOCK:
        conn = _get_conn()
        try:
            conn.executescript(sql)
            conn.commit()
        finally:
            conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row) if row else {}


def monthly_close_get(month: str, pack: str = PACK_LIVE) -> Optional[Dict[str, Any]]:
    """Get state for month (YYYY-MM) and pack (live|paper). R27.1: reads from monthly_close_pack; falls back to monthly_close_state for pack=live."""
    init_monthly_close_db()
    month = (month or "").strip()[:7]
    if len(month) != 7 or month[4] != "-":
        return None
    pack = _norm_pack(pack)
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT month, pack, generated_ts, paths_json FROM monthly_close_pack WHERE month = ? AND pack = ?",
                (month, pack),
            ).fetchone()
            if not row and pack == PACK_LIVE:
                row = conn.execute(
                    "SELECT month, generated_ts, paths_json FROM monthly_close_state WHERE month = ?",
                    (month,),
                ).fetchone()
                if row:
                    d = _row_to_dict(row)
                    d["pack"] = PACK_LIVE
                    try:
                        d["paths_json"] = json.loads(d.get("paths_json") or "[]")
                    except Exception:
                        d["paths_json"] = []
                    return d
            if not row:
                return None
            d = _row_to_dict(row)
            try:
                d["paths_json"] = json.loads(d.get("paths_json") or "[]")
            except Exception:
                d["paths_json"] = []
            return d
        finally:
            conn.close()


def monthly_close_set(month: str, generated_ts: str, paths_json: List[str], pack: str = PACK_LIVE) -> None:
    """Upsert state for month and pack (live|paper). R27.1: writes to monthly_close_pack."""
    init_monthly_close_db()
    month = (month or "").strip()[:7]
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")
    pack = _norm_pack(pack)
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO monthly_close_pack (month, pack, generated_ts, paths_json)
                   VALUES (?, ?, ?, ?)""",
                (month, pack, generated_ts, json.dumps(paths_json)),
            )
            conn.commit()
        finally:
            conn.close()


def _month_range(month: str) -> tuple[str, str]:
    """Return (from_date, to_date) for month YYYY-MM."""
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")
    y, m = int(month[:4]), int(month[5:7])
    last = monthrange(y, m)[1]
    return f"{month}-01", f"{month}-{last:02d}"


def _guardrails_snapshot_safe() -> Dict[str, Any]:
    """Guardrails snapshot with safe numeric/status fields only (no FAIL_/WARN_)."""
    out: Dict[str, Any] = {}
    try:
        from app.core.portfolio.guardrails_r259 import get_guardrails_metrics_and_status
        g = get_guardrails_metrics_and_status()
        out["status"] = g.get("status") or "OK"
        out["total_equity"] = g.get("total_equity")
        out["cash_reserve_pct"] = g.get("cash_reserve_pct")
        out["open_options_count"] = g.get("open_options_count")
        out["open_shares_count"] = g.get("open_shares_count")
        out["symbols_exposure_count"] = g.get("symbols_exposure_count")
    except Exception:
        pass
    return out


def generate_monthly_close_pack(month: str, include_paper: bool = False) -> Dict[str, Any]:
    """
    Generate close pack for month (YYYY-MM). R27.1: include_paper=False -> data/reports/<month>/live/,
    include_paper=True -> .../paper/. Report includes included_paper and mode.
    Creates monthly_report.json, monthly_report.csv, journal_export.csv, summary.txt.
    Returns dict: month, pack, generated_ts, paths, report.
    """
    month = (month or "").strip()[:7]
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")
    from app.core.journal.journal_store import journal_monthly_aggregate, journal_list, journal_monthly_paper_live_counts

    pack = PACK_PAPER if include_paper else PACK_LIVE
    from_date, to_date = _month_range(month)
    generated_ts = datetime.now(timezone.utc).isoformat()
    base = _reports_base_path()
    month_dir = base / month / pack
    month_dir.mkdir(parents=True, exist_ok=True)

    agg = journal_monthly_aggregate(month, include_paper=include_paper)
    entries = journal_list(from_date=from_date, to_date=to_date, limit=10000, offset=0, include_paper=include_paper)
    entries.sort(key=lambda e: (e.get("trade_date") or "", e.get("created_ts") or ""))

    live_count, paper_count = journal_monthly_paper_live_counts(month)
    if live_count and paper_count:
        mode = "MIXED"
    elif paper_count:
        mode = "PAPER_ONLY"
    else:
        mode = "LIVE_ONLY"

    report: Dict[str, Any] = {
        "month": month,
        "generated_ts": generated_ts,
        "included_paper": include_paper,
        "mode": mode,
        "totals": {
            "realized_pl": agg.get("total_realized_pl", 0),
            "fees": agg.get("fees_total", 0),
            "trade_count": agg.get("trade_count", 0),
            "win_rate": agg.get("win_rate", 0),
        },
        "by_strategy": agg.get("by_strategy") or {},
        "winners": agg.get("top_winners") or [],
        "losers": agg.get("top_losers") or [],
    }
    report["guardrails"] = _guardrails_snapshot_safe()

    with open(month_dir / "monthly_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    with open(month_dir / "monthly_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "realized_pl", "fees", "trade_count", "win_rate"])
        w.writerow([
            month,
            report["totals"]["realized_pl"],
            report["totals"]["fees"],
            report["totals"]["trade_count"],
            report["totals"]["win_rate"],
        ])

    if entries:
        keys = list(entries[0].keys())
        with open(month_dir / "journal_export.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            for r in entries:
                writer.writerow(r)
    else:
        with open(month_dir / "journal_export.csv", "w", encoding="utf-8", newline="") as f:
            f.write("id,created_ts,trade_date,symbol,strategy,action,qty,price,premium,fees,contract_key,notes,tags,realized_pl,link_id\n")

    lines = [
        f"Monthly close — {month} ({pack})",
        f"Generated: {generated_ts}",
        f"Realized P/L: {report['totals']['realized_pl']:.2f}",
        f"Fees: {report['totals']['fees']:.2f}",
        f"Trades: {report['totals']['trade_count']} | Win rate: {report['totals']['win_rate']}%",
    ]
    if report.get("by_strategy"):
        lines.append("By strategy: " + ", ".join(f"{k}={v}" for k, v in sorted(report["by_strategy"].items())))
    if report.get("guardrails") and report["guardrails"].get("status"):
        lines.append(f"Guardrails: {report['guardrails']['status']}")
    with open(month_dir / "summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines[:10]))

    paths = ["monthly_report.json", "monthly_report.csv", "journal_export.csv", "summary.txt"]
    monthly_close_set(month, generated_ts, paths, pack=pack)
    return {"month": month, "pack": pack, "generated_ts": generated_ts, "paths": paths, "report": report}
