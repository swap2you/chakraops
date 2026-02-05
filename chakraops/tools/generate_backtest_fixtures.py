#!/usr/bin/env python3
"""Generate dated snapshot fixtures from market_snapshot.csv for backtest smoke testing.

Writes app/data/backtest_fixtures/snapshots/YYYY-MM-DD.csv for each date in the range.
Timestamp column is set to that date at 10:00 ET so backtest can treat each file as a snapshot.

Usage (from repo root):
  python tools/generate_backtest_fixtures.py
  python tools/generate_backtest_fixtures.py --start 2026-01-01 --end 2026-01-10
  python tools/generate_backtest_fixtures.py --days 5   # last 5 days from today

No live data calls. Deterministic: same source CSV + same args -> same outputs.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    import pytz
except ImportError:
    pytz = None

_ET = pytz.timezone("America/New_York") if pytz else None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source_csv(repo: Path) -> Path:
    return repo / "app" / "data" / "snapshots" / "market_snapshot.csv"


def _out_dir(repo: Path) -> Path:
    d = repo / "app" / "data" / "backtest_fixtures" / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _template_rows() -> list[dict]:
    return [
        {"symbol": "SPY", "price": "450", "volume": "38000000", "iv_rank": "22"},
        {"symbol": "QQQ", "price": "140", "volume": "900000", "iv_rank": "25"},
        {"symbol": "AAPL", "price": "185", "volume": "25000000", "iv_rank": "18"},
        {"symbol": "MSFT", "price": "410", "volume": "18000000", "iv_rank": "42"},
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate dated snapshot fixtures for backtest")
    ap.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD")
    ap.add_argument("--end", type=str, default=None, help="End date YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=None, help="Generate this many days (from --end or today)")
    args = ap.parse_args()

    repo = _repo_root()
    src = _source_csv(repo)
    out = _out_dir(repo)

    # Load source rows (symbol, price, volume, iv_rank) — drop timestamp, we set it per date
    if src.exists():
        with open(src, "r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            fn = [x for x in (r.fieldnames or []) if x != "timestamp"]
            need = {"symbol", "price", "volume", "iv_rank"}
            if need - set(fn):
                rows = _template_rows()
            else:
                rows = []
                for row in r:
                    if not (row.get("symbol") or "").strip():
                        continue
                    rows.append({k: row.get(k, "") for k in fn})
                if not rows:
                    rows = _template_rows()
    else:
        rows = _template_rows()
        print(f"[INFO] No {src.name}; using template ({len(rows)} rows)", file=sys.stderr)

    # Date range
    if args.end:
        end = date.fromisoformat(args.end)
    else:
        end = date.today()
    if args.days is not None:
        start = end - timedelta(days=args.days - 1)
    elif args.start:
        start = date.fromisoformat(args.start)
        if not args.end:
            end = start + timedelta(days=6)  # default 7 days
    else:
        start = end - timedelta(days=6)  # default 7 days

    if start > end:
        start, end = end, start

    # Write one CSV per date
    fieldnames = ["symbol", "price", "volume", "iv_rank", "timestamp"]
    if _ET:
        def _ts(d: date) -> str:
            from datetime import datetime
            return datetime(d.year, d.month, d.day, 10, 0, 0, tzinfo=_ET).isoformat()
    else:
        def _ts(d: date) -> str:
            return f"{d.isoformat()}T10:00:00"

    written = 0
    d = start
    while d <= end:
        path = out / f"{d.isoformat()}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in rows:
                out_row = {k: row.get(k, "") for k in fieldnames}
                out_row["timestamp"] = _ts(d)
                w.writerow(out_row)
        written += 1
        d += timedelta(days=1)

    print(f"OK: wrote {written} snapshots to {out} ({start.isoformat()} .. {end.isoformat()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
