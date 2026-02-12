# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
EOD chain snapshot job (Phase 3.1.3).

Fetches ORATS chain for each symbol in the universe and stores metadata under
artifacts/runs/YYYY-MM-DD/eod_chain/. Runs at 16:05 ET on trading days (scheduler in server).
If no chain available for a symbol, logs a warning and continues (does not block).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import List

from app.core.eval.run_artifacts import _artifacts_runs_root

logger = logging.getLogger(__name__)


def get_eod_chain_dir(as_of_date: date) -> Path:
    """Return artifacts/runs/YYYY-MM-DD/eod_chain/ for the given date."""
    root = _artifacts_runs_root()
    date_str = as_of_date.strftime("%Y-%m-%d")
    return root / date_str / "eod_chain"


def run_eod_chain_snapshot(as_of_date: date, symbols: List[str]) -> dict:
    """
    Fetch ORATS chain for each symbol and write metadata to artifacts/runs/YYYY-MM-DD/eod_chain/.

    File naming: SYMBOL_chain_YYYYMMDD_1600ET.json.
    Metadata: symbol, as_of, source, expiration_count, contract_count, required_fields_present.
    If no chain is available for a symbol, log warning and continue (do not block).

    Returns:
        Dict with keys: written (int), skipped (int), errors (int), path (str).
    """
    from app.core.options.orats_chain_pipeline import fetch_base_chain

    eod_dir = get_eod_chain_dir(as_of_date)
    eod_dir.mkdir(parents=True, exist_ok=True)
    date_part = as_of_date.strftime("%Y%m%d")
    as_of_iso = as_of_date.isoformat()

    written = 0
    skipped = 0
    errors = 0

    for symbol in symbols:
        if not (symbol or "").strip():
            continue
        sym = symbol.strip().upper()
        try:
            contracts, _, err = fetch_base_chain(sym)
            if err:
                logger.warning("[EOD_CHAIN] No chain for %s: %s", sym, err)
                skipped += 1
                continue
            if not contracts:
                logger.warning("[EOD_CHAIN] No chain for %s: empty result", sym)
                skipped += 1
                continue
            expirations = {c.expiration for c in contracts}
            expiration_count = len(expirations)
            contract_count = len(contracts)
            required_fields_present = contract_count > 0
            meta = {
                "symbol": sym,
                "as_of": as_of_iso,
                "source": "EOD_SNAPSHOT",
                "expiration_count": expiration_count,
                "contract_count": contract_count,
                "required_fields_present": required_fields_present,
            }
            filename = f"{sym}_chain_{date_part}_1600ET.json"
            path = eod_dir / filename
            with open(path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, default=str)
                f.flush()
            written += 1
        except Exception as e:
            logger.warning("[EOD_CHAIN] Error fetching chain for %s: %s", sym, e, exc_info=False)
            errors += 1

    if written or skipped or errors:
        logger.info(
            "[EOD_CHAIN] Snapshot complete: written=%d skipped=%d errors=%d path=%s",
            written, skipped, errors, str(eod_dir),
        )
    return {
        "written": written,
        "skipped": skipped,
        "errors": errors,
        "path": str(eod_dir),
    }


def should_run_eod_chain_today(et_date: date) -> bool:
    """
    Return True if the given date (in ET) is a trading day (weekday, not holiday).
    Used by the scheduler to run only on trading days; Friday runs normally.
    """
    from app.core.environment.market_calendar import is_market_open_today
    return is_market_open_today(et_date)


__all__ = [
    "get_eod_chain_dir",
    "run_eod_chain_snapshot",
    "should_run_eod_chain_today",
]
