# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""DEV-only: seed market snapshot CSV from last close (EOD) without Theta.

Writes app/data/snapshots/market_snapshot.csv for consumption by the
existing Build New Snapshot flow. Does not write to the DB.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import pytz
except ImportError:
    pytz = None

_ET_TZ = pytz.timezone("America/New_York") if pytz else None

# Default CSV path (compatible with existing snapshot ingestion)
def _default_csv_path() -> Path:
    from app.core.config.paths import BASE_DIR
    return BASE_DIR / "app" / "data" / "snapshots" / "market_snapshot.csv"


def _default_symbols_path() -> Path:
    from app.core.config.paths import BASE_DIR
    return BASE_DIR / "app" / "data" / "default_universe.txt"


def load_default_universe() -> List[str]:
    """Load symbol list from app/data/default_universe.txt. SPY and QQQ are always included."""
    path = _default_symbols_path()
    symbols: List[str] = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    symbols.append(s.upper())
    benchmarks = ["SPY", "QQQ"]
    for b in benchmarks:
        if b not in symbols:
            symbols.insert(0, b)
    return symbols


def seed_snapshot_from_last_close(
    symbols: Optional[List[str]] = None,
    csv_path: Optional[Path] = None,
    timeout_seconds: int = 10,
) -> Tuple[Path, int]:
    """Fetch last close and volume for symbols via yfinance, write snapshot CSV.

    Does not write to the DB. Output is compatible with existing CSV ingestion
    (symbol, price, volume, iv_rank, timestamp). iv_rank is set to 50 when
    no source exists.

    Parameters
    ----------
    symbols : optional list of symbols. If None, uses load_default_universe().
    csv_path : output path. If None, uses app/data/snapshots/market_snapshot.csv.
    timeout_seconds : not used by yfinance; kept for API consistency.

    Returns
    -------
    (path, symbol_count) where symbol_count is the number of rows written.

    Raises
    ------
    RuntimeError
        If yfinance is unavailable or CSV write fails.
    """
    try:
        from app.data.yfinance_provider import YFinanceProvider
    except ImportError as e:
        raise RuntimeError(
            "yfinance is required for Seed Snapshot from Last Close. "
            "Install with: pip install yfinance"
        ) from e

    if symbols is None:
        symbols = load_default_universe()
    if not symbols:
        raise ValueError("Symbol list is empty and default_universe.txt has no symbols")

    out_path = csv_path or _default_csv_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    provider = YFinanceProvider()
    rows: List[dict] = []
    now_et = datetime.now(_ET_TZ) if _ET_TZ else datetime.now(timezone.utc)
    ts_iso = now_et.isoformat()

    for sym in symbols:
        sym_upper = sym.strip().upper()
        if not sym_upper:
            continue
        try:
            df = provider.get_daily(sym_upper, lookback=5)
            if df is None or df.empty:
                logger.warning("[DEV_SEED] No data for %s, skipping", sym_upper)
                continue
            last = df.iloc[-1]
            price = float(last["close"]) if "close" in last and last.get("close") is not None else None
            volume = float(last["volume"]) if "volume" in last and last.get("volume") is not None else 0.0
            if price is None or price <= 0:
                logger.warning("[DEV_SEED] Invalid price for %s, skipping", sym_upper)
                continue
            rows.append({
                "symbol": sym_upper,
                "price": price,
                "volume": volume,
                "iv_rank": 50,  # placeholder when no IV source
                "timestamp": ts_iso,
            })
        except Exception as e:
            logger.warning("[DEV_SEED] Failed to fetch %s: %s", sym_upper, e)

    if not rows:
        raise RuntimeError("No symbols could be fetched; CSV not written")

    import csv as csv_module
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv_module.DictWriter(f, fieldnames=["symbol", "price", "volume", "iv_rank", "timestamp"])
        w.writeheader()
        w.writerows(rows)

    logger.info("[DEV_SEED] Wrote %s with %d symbols", out_path, len(rows))
    return (out_path, len(rows))
