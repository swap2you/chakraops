#!/usr/bin/env python3
"""Generate app/data/fixtures/eod_seed.csv from market_snapshot.csv or a template.

Run from repo root:
  python tools/generate_eod_seed_fixture.py

If app/data/snapshots/market_snapshot.csv exists, copies it (normalizing columns)
into app/data/fixtures/eod_seed.csv. Otherwise writes a minimal template with
SPY, QQQ and placeholders. Columns: symbol, price, volume, iv_rank, timestamp (ET ISO).
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import pytz
except ImportError:
    pytz = None

_ET = pytz.timezone("America/New_York") if pytz else None


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def _template_rows() -> list[dict]:
    ts = (datetime.now(_ET).isoformat() if _ET else datetime.now(timezone.utc).isoformat())
    return [
        {"symbol": "SPY", "price": "450", "volume": "38000000", "iv_rank": "22", "timestamp": ts},
        {"symbol": "QQQ", "price": "140", "volume": "900000", "iv_rank": "25", "timestamp": ts},
        {"symbol": "AAPL", "price": "185", "volume": "25000000", "iv_rank": "18", "timestamp": ts},
        {"symbol": "MSFT", "price": "410", "volume": "18000000", "iv_rank": "42", "timestamp": ts},
    ]


def main() -> int:
    repo = _repo()
    snapshot_csv = repo / "app" / "data" / "snapshots" / "market_snapshot.csv"
    fixture_dir = repo / "app" / "data" / "fixtures"
    fixture_path = fixture_dir / "eod_seed.csv"
    fixture_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict]
    if snapshot_csv.exists():
        with open(snapshot_csv, "r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            fn = r.fieldnames or []
            need = {"symbol", "price", "volume", "iv_rank", "timestamp"}
            if need - set(fn):
                print(
                    f"[WARN] Snapshot CSV missing columns {need - set(fn)}; "
                    "using template.",
                    file=sys.stderr,
                )
                rows = _template_rows()
            else:
                rows = [row for row in r if row.get("symbol", "").strip()]
                if not rows:
                    rows = _template_rows()
                else:
                    ts = datetime.now(_ET).isoformat() if _ET else datetime.now(timezone.utc).isoformat()
                    for row in rows:
                        if "timestamp" not in row or not (row.get("timestamp") or "").strip():
                            row["timestamp"] = ts
    else:
        rows = _template_rows()
        print(
            f"[INFO] No {snapshot_csv.name}; writing template to {fixture_path}",
            file=sys.stderr,
        )

    with open(fixture_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["symbol", "price", "volume", "iv_rank", "timestamp"]
        )
        w.writeheader()
        w.writerows(rows)
    print(f"OK: {fixture_path} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
