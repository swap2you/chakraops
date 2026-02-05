# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Snapshot-only provider (LAST RESORT). Uses latest stored decision snapshot prices."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.market.providers.base import MarketDataProviderInterface

logger = logging.getLogger(__name__)


def _default_out_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "out"


def _load_latest_snapshot_prices(out_dir: Path) -> Dict[str, float]:
    """Extract symbol -> underlying_price from latest decision_*.json selected_signals/candidates."""
    prices: Dict[str, float] = {}
    if not out_dir.exists() or not out_dir.is_dir():
        return prices
    jsons = sorted(
        [p for p in out_dir.iterdir() if p.is_file() and p.suffix.lower() == ".json" and p.name.startswith("decision_")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in jsons[:1]:
        try:
            with open(path, "r") as f:
                data = json.load(f)
            snap = data.get("decision_snapshot") or {}
            for item in (snap.get("selected_signals") or []) + (snap.get("scored_candidates") or [])[:100]:
                if not isinstance(item, dict):
                    continue
                cand = (item.get("scored") or {}).get("candidate") or {}
                if not isinstance(cand, dict):
                    continue
                sym = cand.get("symbol")
                up = cand.get("underlying_price")
                if sym and up is not None and isinstance(up, (int, float)) and float(up) > 0:
                    prices[str(sym)] = float(up)
        except Exception as e:
            logger.debug("snapshot_only load %s: %s", path.name, e)
    return prices


class SnapshotOnlyProvider(MarketDataProviderInterface):
    """Last resort: prices from latest decision snapshot only. No live chain."""

    def __init__(self, out_dir: Optional[Path] = None) -> None:
        self.out_dir = out_dir or _default_out_dir()
        self._cache: Dict[str, float] = {}
        self._cache_ok = False

    def health_check(self) -> Tuple[bool, str]:
        self._cache = _load_latest_snapshot_prices(self.out_dir)
        self._cache_ok = len(self._cache) > 0
        if self._cache_ok:
            return True, f"snapshot only ({len(self._cache)} symbols from latest decision)"
        return True, "snapshot only (no decision file yet)"

    def fetch_underlying_prices(self, symbols: List[str]) -> Dict[str, float]:
        if not self._cache_ok:
            self._cache = _load_latest_snapshot_prices(self.out_dir)
            self._cache_ok = True
        return {s: self._cache[s] for s in symbols if s and isinstance(s, str) and s in self._cache}

    def fetch_option_chain_availability(self, symbols: List[str]) -> Dict[str, bool]:
        return {s: False for s in symbols if s and isinstance(s, str)}


__all__ = ["SnapshotOnlyProvider", "_load_latest_snapshot_prices"]
