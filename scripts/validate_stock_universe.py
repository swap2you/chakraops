#!/usr/bin/env python3
"""Phase 2 validation: deterministic stock universe + snapshot contract.

This script:
- Never touches UI
- Never requires market open
- Does not run any CSP/CC logic

It prints:
- total symbols
- eligible symbols
- excluded symbols with reasons
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to path so `import app...` works when running as a script
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from app.core.market.stock_universe import StockUniverseManager
from app.data.stock_snapshot_provider import StockSnapshotProvider


def main() -> int:
    provider = StockSnapshotProvider(timeout_s=5.0)
    universe = StockUniverseManager(provider, allow_etfs=False)

    all_syms = universe.get_all_symbols()
    eligible = universe.get_eligible_stocks()
    eligible_syms = {s.symbol for s in eligible}

    print("== Phase 2: Stock Universe Validation ==")
    print(f"Total symbols: {len(all_syms)}")
    print(f"Eligible symbols: {len(eligible)}")
    print()

    print("Eligible:")
    for s in sorted(eligible, key=lambda x: x.symbol):
        print(
            f"- {s.symbol} price={s.price} bid={s.bid} ask={s.ask} "
            f"vol={s.volume} avg_vol={s.avg_volume} has_options={s.has_options}"
        )
    print()

    print("Excluded:")
    excluded = [sym for sym in all_syms if sym not in eligible_syms]
    for sym in excluded:
        reason = universe.explain_exclusion(sym)
        print(f"- {sym}: {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

