#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 offline walk-forward simulation CLI (SIMULATION / manual_only).

Usage (from chakraops package dir):
  python scripts/run_r40_simulation.py --profile balanced \\
    --fixture-dir tests/fixtures/r40 \\
    --train-start 2024-01-01 --train-end 2024-06-30 \\
    --oos-start 2024-07-01 --oos-end 2024-12-31

Writes summary JSON under out/r40/ or data/reports/r40/ (gitignored).
No live ORATS; no broker writes; scheduler untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_CHAKRAOPS_ROOT = _SCRIPT_DIR.parent
if str(_CHAKRAOPS_ROOT) not in sys.path:
    sys.path.insert(0, str(_CHAKRAOPS_ROOT))


def _default_out_dir() -> Path:
    # Prefer repo-level out/ (parent of package), else package data/reports
    repo_out = _CHAKRAOPS_ROOT.parent / "out" / "r40"
    if (_CHAKRAOPS_ROOT.parent / "out").exists() or True:
        return repo_out
    return _CHAKRAOPS_ROOT / "data" / "reports" / "r40"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="R40 Strategy Lab walk-forward SIMULATION (offline)")
    p.add_argument("--profile", default="balanced", help="Strategy profile name")
    p.add_argument("--fixture-dir", type=Path, default=None, help="Fixture directory (trades.json and/or snapshot CSVs)")
    p.add_argument("--trades-fixture", type=Path, default=None, help="Explicit trades JSON path")
    p.add_argument("--train-start", required=True, help="Train window start YYYY-MM-DD")
    p.add_argument("--train-end", required=True, help="Train window end YYYY-MM-DD")
    p.add_argument("--oos-start", required=True, help="OOS window start YYYY-MM-DD")
    p.add_argument("--oos-end", required=True, help="OOS window end YYYY-MM-DD")
    p.add_argument("--account-capital", type=float, default=150_000.0)
    p.add_argument("--out-dir", type=Path, default=None, help="Output directory (default out/r40)")
    p.add_argument("--include-trades", action="store_true", help="Include trade rows in JSON")
    args = p.parse_args(argv)

    from app.core.backtest.r40.walk_forward import run_walk_forward, summarize_for_report

    result = run_walk_forward(
        profile=args.profile,
        fixture_dir=args.fixture_dir,
        trades_fixture=args.trades_fixture,
        train_start=args.train_start,
        train_end=args.train_end,
        oos_start=args.oos_start,
        oos_end=args.oos_end,
        account_capital=args.account_capital,
    )
    summary = summarize_for_report(result)
    if args.include_trades:
        summary["train_trades"] = result.train_trades
        summary["oos_trades"] = result.oos_trades

    out_dir = args.out_dir or _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"r40_walk_forward_{args.profile}_{ts}.json"
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Also write a stable "latest" pointer for UI optional section
    latest = out_dir / "r40_last_run.json"
    latest.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("SIMULATION — NOT A LIVE RECOMMENDATION")
    print(f"profile={args.profile} source={result.source}")
    print(f"train metrics: {json.dumps(result.train_metrics, sort_keys=True)}")
    print(f"oos metrics:   {json.dumps(result.oos_metrics, sort_keys=True)}")
    print(f"wrote {out_path}")
    print(f"wrote {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
