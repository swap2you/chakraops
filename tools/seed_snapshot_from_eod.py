#!/usr/bin/env python3
"""CLI to seed market_snapshot.csv from fixture or last close (yfinance). DEV-only, no DB writes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure app is on path when run as script
_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed market_snapshot.csv (fixture or yfinance, DEV)")
    parser.add_argument(
        "--from-fixture",
        action="store_true",
        help="Use app/data/fixtures/eod_seed.csv (no yfinance)",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Symbols to fetch (yfinance only); if omitted, use default_universe.txt",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path; default app/data/snapshots/market_snapshot.csv",
    )
    args = parser.parse_args()

    try:
        if args.from_fixture:
            from app.core.dev_seed import seed_snapshot_from_fixture
            path, count = seed_snapshot_from_fixture(out_path=args.out)
        else:
            from app.core.dev_seed import seed_snapshot_from_last_close
            path, count = seed_snapshot_from_last_close(symbols=args.symbols or None, csv_path=args.out)
        print(f"OK: wrote {path} ({count} symbols)")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
