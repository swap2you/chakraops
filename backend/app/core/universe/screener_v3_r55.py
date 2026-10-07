# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R55 dynamic universe screener V3 — provenance-honest; no threshold retune."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def screen_universe_v3(
    symbols: List[Dict[str, Any]],
    *,
    min_liquidity_rank: Optional[float] = None,
    require_options: bool = False,
) -> Dict[str, Any]:
    """Filter candidate symbols with explicit criteria provenance.

    Does not mutate production threshold profiles.
    """
    out_rows: List[Dict[str, Any]] = []
    for row in symbols or []:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").upper().strip()
        if not sym:
            continue
        reasons: List[str] = []
        include = True
        liq = row.get("liquidity_rank")
        if min_liquidity_rank is not None:
            try:
                if float(liq) < float(min_liquidity_rank):
                    include = False
                    reasons.append("below_min_liquidity_rank")
                else:
                    reasons.append("liquidity_ok")
            except (TypeError, ValueError):
                include = False
                reasons.append("liquidity_missing")
        if require_options and not row.get("has_options"):
            include = False
            reasons.append("options_required")
        elif require_options:
            reasons.append("options_ok")
        out_rows.append(
            {
                "symbol": sym,
                "include": include,
                "reasons": reasons,
                "inputs": {"liquidity_rank": liq, "has_options": row.get("has_options")},
            }
        )
    return {
        "schema": "universe_screener_v3",
        "criteria": {
            "min_liquidity_rank": min_liquidity_rank,
            "require_options": require_options,
        },
        "threshold_retune": False,
        "provenance": "explicit_request_criteria_only",
        "rows": out_rows,
        "manual_only": True,
        "trade_execution": False,
    }
