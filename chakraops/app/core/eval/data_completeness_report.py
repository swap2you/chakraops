# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 4: Data completeness report per evaluation run.

Emitted as JSON alongside the run file: per-symbol missing_fields, waived_fields,
source_endpoints; aggregate % symbols missing bid/ask, volume, etc.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def build_data_completeness_report(symbols: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build data completeness report from run symbols (list of symbol dicts).

    Each symbol dict is expected to have: symbol, missing_fields (list),
    data_sources (dict or None), waiver_reason (optional).
    """
    per_symbol: List[Dict[str, Any]] = []
    n = len(symbols) or 1
    missing_bid_ask = 0
    missing_volume = 0
    missing_price = 0
    has_waiver = 0
    endpoints_used: Dict[str, int] = {}

    for s in symbols:
        sym = (s.get("symbol") or "").strip()
        missing = list(s.get("missing_fields") or [])
        data_sources = s.get("data_sources") or {}
        waiver = s.get("waiver_reason")
        waived = list(data_sources.keys()) if waiver and data_sources else []
        if waiver and not waived:
            waived = ["bid", "ask", "volume"]  # conservative when waiver set
        sources = list(set(v for v in (data_sources.values() or []) if v)) if isinstance(data_sources, dict) else []
        if isinstance(data_sources, dict):
            for v in data_sources.values():
                if v and v != "waived":
                    endpoints_used[v] = endpoints_used.get(v, 0) + 1

        per_symbol.append({
            "symbol": sym,
            "missing_fields": missing,
            "waived_fields": waived,
            "source_endpoints": sources,
        })

        if "bid" in missing or "ask" in missing:
            missing_bid_ask += 1
        if "volume" in missing:
            missing_volume += 1
        if "stockPrice" in missing or "price" in missing:
            missing_price += 1
        if waiver:
            has_waiver += 1

    aggregate = {
        "total_symbols": n,
        "pct_missing_bid_ask": round(100.0 * missing_bid_ask / n, 2),
        "pct_missing_volume": round(100.0 * missing_volume / n, 2),
        "pct_missing_price": round(100.0 * missing_price / n, 2),
        "pct_with_waiver": round(100.0 * has_waiver / n, 2),
        "count_missing_bid_ask": missing_bid_ask,
        "count_missing_volume": missing_volume,
        "count_missing_price": missing_price,
        "count_with_waiver": has_waiver,
        "endpoints_used": endpoints_used,
    }

    return {
        "per_symbol": per_symbol,
        "aggregate": aggregate,
    }


def write_data_completeness_report(
    run_id: str,
    symbols: List[Dict[str, Any]],
    evaluations_dir: Path | None = None,
) -> Path:
    """
    Write data completeness report JSON next to the run file.
    Returns path of written file.
    """
    try:
        from app.core.eval.evaluation_store import _get_evaluations_dir
        base = evaluations_dir or _get_evaluations_dir()
    except ImportError:
        base = Path("out") / "evaluations"
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{run_id}_data_completeness.json"
    report = build_data_completeness_report(symbols)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info("[DATA_COMPLETENESS] Wrote %s", path)
    return path
