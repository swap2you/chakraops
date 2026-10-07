# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.6: Static Sector/Cluster Mapping V1.

Informational only. No broker integration, no web calls.
Unknown symbol -> cluster="UNKNOWN", sector="UNKNOWN".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Pragmatic starter set — editable, additive
DEFAULT_CLUSTER_GROUPS: Dict[str, list[str]] = {
    "MEGA_CAP_TECH": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"],
    "SEMIS": ["AMD", "AVGO", "QCOM", "INTC"],
    "FINANCIALS": ["JPM", "BAC", "WFC", "GS", "MS"],
    "ENERGY": ["XOM", "CVX"],
    "ENERGY_ETF": ["XLE"],
    "HEALTHCARE": ["JNJ", "UNH", "PFE"],
    "INDEX_ETF": ["SPY", "QQQ", "IWM", "DIA"],
    "VOL_ETF": ["VIXY"],
    "DIVIDEND_YIELD": ["KO", "PG", "PEP"],
}

# Cluster -> sector mapping for default groups
_CLUSTER_TO_SECTOR: Dict[str, str] = {
    "MEGA_CAP_TECH": "TECH",
    "SEMIS": "TECH",
    "FINANCIALS": "FIN",
    "ENERGY": "ENERGY",
    "ENERGY_ETF": "ENERGY",
    "HEALTHCARE": "HEALTH",
    "INDEX_ETF": "ETF",
    "VOL_ETF": "ETF",
    "DIVIDEND_YIELD": "CONS_STAPLES",
}

DEFAULT_CLUSTER_MAP: Dict[str, Dict[str, str]] = {}
for cluster, symbols in DEFAULT_CLUSTER_GROUPS.items():
    sector = _CLUSTER_TO_SECTOR.get(cluster, "OTHER")
    for sym in symbols:
        DEFAULT_CLUSTER_MAP[sym.upper()] = {"cluster": cluster, "sector": sector}


def get_symbol_tags(
    symbol: str,
    override_map: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, str]:
    """
    Return cluster and sector tags for a symbol.

    Args:
        symbol: Ticker symbol (case-insensitive for lookup).
        override_map: Optional map of symbol -> {"cluster": str, "sector": str}.
            Takes precedence over DEFAULT_CLUSTER_MAP.

    Returns:
        {"cluster": str, "sector": str, "source": "DEFAULT"|"OVERRIDE"|"UNKNOWN"}
    """
    if not symbol or not isinstance(symbol, str):
        return {"cluster": "UNKNOWN", "sector": "UNKNOWN", "source": "UNKNOWN"}
    sym_upper = symbol.strip().upper()
    if not sym_upper:
        return {"cluster": "UNKNOWN", "sector": "UNKNOWN", "source": "UNKNOWN"}

    if override_map:
        entry = override_map.get(sym_upper)
        if isinstance(entry, dict):
            cluster = entry.get("cluster") or "UNKNOWN"
            sector = entry.get("sector") or "UNKNOWN"
            return {"cluster": str(cluster), "sector": str(sector), "source": "OVERRIDE"}

    entry = DEFAULT_CLUSTER_MAP.get(sym_upper)
    if entry:
        return {
            "cluster": entry.get("cluster") or "UNKNOWN",
            "sector": entry.get("sector") or "UNKNOWN",
            "source": "DEFAULT",
        }
    return {"cluster": "UNKNOWN", "sector": "UNKNOWN", "source": "UNKNOWN"}


def load_cluster_map(path: Union[str, Path]) -> Dict[str, Dict[str, str]]:
    """
    Load cluster map from JSON file.

    Args:
        path: Path to artifacts/config/cluster_map.json (or similar).

    Returns:
        Dict symbol -> {"cluster": str, "sector": str}. Empty dict if file missing.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, dict):
            cluster = v.get("cluster")
            sector = v.get("sector")
            if cluster is not None or sector is not None:
                out[k.upper()] = {
                    "cluster": str(cluster) if cluster is not None else "UNKNOWN",
                    "sector": str(sector) if sector is not None else "UNKNOWN",
                }
    return out
