# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Canonical per-ticker SymbolSnapshot — the ONLY module that composes equity + core + derived data.

Universe, Ticker, Evaluation, and Decision artifacts must use this service. Data comes from:
- Delayed equity quote: price, bid, ask, volume, quote_date (strikes/options with underlying)
- Delayed iv_rank (ivrank endpoint)
- Core Data: stock_volume_today (stkVolu), avg_option_volume_20d (avgOptVolu20d) via /datav2/cores
- Optional derived: avg_stock_volume_20d from /datav2/hist/dailies (mean of last 20 days)

Never uses /datav2/live/* for equity bid/ask/volume or iv_rank. Never emits "UNKNOWN"; use null + missing_reasons.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Per-run cache: (ticker, section, date_key) -> result to avoid spamming ORATS
_snapshot_cache: Dict[str, Any] = {}
_CACHE_KEY_QUOTE = "quote"
_CACHE_KEY_CORE = "core"
_CACHE_KEY_DERIVED = "derived"


def _cache_key(ticker: str, section: str, date_key: str) -> str:
    return f"{ticker.upper()}:{section}:{date_key}"


@dataclass
class SymbolSnapshot:
    """
    Single canonical snapshot per ticker. All fields from delayed quote, core, or explicit derived/missing.
    """
    ticker: str
    # Delayed quote (strikes/options + ivrank)
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    quote_date: Optional[str] = None
    iv_rank: Optional[float] = None
    # Core Data (/datav2/cores)
    stock_volume_today: Optional[int] = None
    avg_option_volume_20d: Optional[float] = None
    # Optional derived (hist/dailies)
    avg_stock_volume_20d: Optional[float] = None
    # Provenance
    quote_as_of: Optional[str] = None
    core_as_of: Optional[str] = None
    derived_as_of: Optional[str] = None
    field_sources: Dict[str, str] = field(default_factory=dict)
    missing_reasons: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "ticker": self.ticker,
            "price": self.price,
            "bid": self.bid,
            "ask": self.ask,
            "volume": self.volume,
            "quote_date": self.quote_date,
            "iv_rank": self.iv_rank,
            "stock_volume_today": self.stock_volume_today,
            "avg_option_volume_20d": self.avg_option_volume_20d,
            "avg_stock_volume_20d": self.avg_stock_volume_20d,
            "quote_as_of": self.quote_as_of,
            "core_as_of": self.core_as_of,
            "derived_as_of": self.derived_as_of,
            "field_sources": dict(self.field_sources),
            "missing_reasons": dict(self.missing_reasons),
        }
        return out


def _coerce_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def get_snapshot(
    ticker: str,
    *,
    derive_avg_stock_volume_20d: bool = True,
    use_cache: bool = True,
) -> SymbolSnapshot:
    """
    Build canonical SymbolSnapshot for one ticker. Uses delayed quote + core + optional derived.
    Never uses /datav2/live/* for equity or iv_rank. Never returns "UNKNOWN"; use null + missing_reasons.
    """
    from app.core.data.orats_client import fetch_full_equity_snapshots
    from app.core.orats.orats_core_client import fetch_core_snapshot, derive_avg_stock_volume_20d as _derive_avg
    from app.core.config.orats_secrets import ORATS_API_TOKEN

    sym = (ticker or "").strip().upper()
    if not sym:
        s = SymbolSnapshot(ticker="")
        s.missing_reasons["ticker"] = "Ticker is required"
        return s

    now_iso = datetime.now(timezone.utc).isoformat()
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    token = (ORATS_API_TOKEN or "").strip()

    snapshot = SymbolSnapshot(ticker=sym)

    # --- Delayed quote + iv_rank (strikes/options + ivrank) ---
    try:
        full = fetch_full_equity_snapshots([sym])
        delayed = full.get(sym) if full else None
    except Exception as e:
        logger.warning("[SYMBOL_SNAPSHOT] %s delayed quote failed: %s", sym, e)
        delayed = None

    if delayed:
        snapshot.price = _coerce_float(getattr(delayed, "price", None))
        snapshot.bid = _coerce_float(getattr(delayed, "bid", None))
        snapshot.ask = _coerce_float(getattr(delayed, "ask", None))
        snapshot.volume = _coerce_int(getattr(delayed, "volume", None))
        snapshot.quote_date = getattr(delayed, "quote_date", None) or None
        snapshot.iv_rank = _coerce_float(getattr(delayed, "iv_rank", None))
        snapshot.quote_as_of = snapshot.quote_date or now_iso
        for f in ("price", "bid", "ask", "volume", "quote_date", "iv_rank"):
            if getattr(snapshot, f) is not None:
                snapshot.field_sources[f] = "delayed_strikes_ivrank"
        if snapshot.price is None:
            snapshot.missing_reasons["price"] = "Not provided by ORATS delayed quote"
        if snapshot.volume is None:
            snapshot.missing_reasons["volume"] = "Not provided by ORATS delayed quote"
        if snapshot.quote_date is None:
            snapshot.missing_reasons["quote_date"] = "Not provided by ORATS delayed quote"
        if snapshot.iv_rank is None:
            snapshot.missing_reasons["iv_rank"] = "Not provided by ORATS delayed quote"
        logger.info(
            "[SYMBOL_SNAPSHOT] %s quote endpoint=delayed_strikes_ivrank price=%s volume=%s iv_rank=%s quote_date=%s",
            sym, snapshot.price, snapshot.volume, snapshot.iv_rank, snapshot.quote_date,
        )
    else:
        for f in ("price", "bid", "ask", "volume", "quote_date", "iv_rank"):
            snapshot.missing_reasons[f] = "Delayed quote fetch failed or empty"
        snapshot.quote_as_of = now_iso

    # --- Core Data (stkVolu, avgOptVolu20d) ---
    cache_key_core = _cache_key(sym, _CACHE_KEY_CORE, date_key)
    if use_cache and cache_key_core in _snapshot_cache:
        core_row = _snapshot_cache[cache_key_core]
    else:
        core_row = None
        if token:
            try:
                core_row = fetch_core_snapshot(sym, ["ticker", "stkVolu", "avgOptVolu20d"], token)
                if use_cache:
                    _snapshot_cache[cache_key_core] = core_row
            except Exception as e:
                logger.warning("[SYMBOL_SNAPSHOT] %s core fetch failed: %s", sym, e)
                core_row = None

    if core_row is not None:
        snapshot.stock_volume_today = _coerce_int(core_row.get("stkVolu"))
        snapshot.avg_option_volume_20d = _coerce_float(core_row.get("avgOptVolu20d"))
        snapshot.core_as_of = now_iso
        if snapshot.stock_volume_today is not None:
            snapshot.field_sources["stock_volume_today"] = "datav2/cores"
        if snapshot.avg_option_volume_20d is not None:
            snapshot.field_sources["avg_option_volume_20d"] = "datav2/cores"
        if snapshot.stock_volume_today is None:
            snapshot.missing_reasons["stock_volume_today"] = "Not provided by ORATS Core Data (stkVolu)"
        if snapshot.avg_option_volume_20d is None:
            snapshot.missing_reasons["avg_option_volume_20d"] = "Not provided by ORATS Core Data (avgOptVolu20d)"
        logger.info(
            "[SYMBOL_SNAPSHOT] %s core endpoint=datav2/cores stkVolu=%s avgOptVolu20d=%s",
            sym, snapshot.stock_volume_today, snapshot.avg_option_volume_20d,
        )
    else:
        snapshot.core_as_of = now_iso
        snapshot.missing_reasons["stock_volume_today"] = "Not provided by ORATS Core Data"
        snapshot.missing_reasons["avg_option_volume_20d"] = "Not provided by ORATS Core Data"

    # --- Optional derived: avg_stock_volume_20d from hist/dailies ---
    if derive_avg_stock_volume_20d and token:
        cache_key_derived = _cache_key(sym, _CACHE_KEY_DERIVED, date_key)
        if use_cache and cache_key_derived in _snapshot_cache:
            snapshot.avg_stock_volume_20d = _snapshot_cache[cache_key_derived]
            snapshot.derived_as_of = now_iso
            if snapshot.avg_stock_volume_20d is not None:
                snapshot.field_sources["avg_stock_volume_20d"] = "DERIVED_ORATS_HIST"
        else:
            try:
                avg = _derive_avg(sym, token, trade_date=snapshot.quote_date or None)
                if use_cache:
                    _snapshot_cache[cache_key_derived] = avg
                if avg is not None:
                    snapshot.avg_stock_volume_20d = avg
                    snapshot.field_sources["avg_stock_volume_20d"] = "DERIVED_ORATS_HIST"
                    snapshot.missing_reasons.pop("avg_stock_volume_20d", None)
                else:
                    snapshot.missing_reasons["avg_stock_volume_20d"] = "Derived from hist/dailies failed or insufficient data"
                snapshot.derived_as_of = now_iso
            except Exception as e:
                snapshot.missing_reasons["avg_stock_volume_20d"] = f"Derived calculation failed: {e}"
                snapshot.derived_as_of = now_iso

    # Per-symbol snapshot summary (TASK D: endpoints called, as_of, fields present)
    endpoints_called = []
    if delayed is not None:
        endpoints_called.append("delayed_strikes_ivrank")
    if core_row is not None:
        endpoints_called.append("datav2/cores")
    if snapshot.field_sources.get("avg_stock_volume_20d"):
        endpoints_called.append("datav2/hist/dailies")
    fields_present = [f for f in ("price", "bid", "ask", "volume", "quote_date", "iv_rank", "stock_volume_today", "avg_option_volume_20d", "avg_stock_volume_20d") if getattr(snapshot, f, None) is not None]
    logger.debug(
        "[SYMBOL_SNAPSHOT] %s endpoints=%s quote_as_of=%s core_as_of=%s derived_as_of=%s fields_present=%s",
        sym, endpoints_called, snapshot.quote_as_of, snapshot.core_as_of, snapshot.derived_as_of, fields_present,
    )
    return snapshot


def get_snapshots_batch(
    tickers: List[str],
    *,
    derive_avg_stock_volume_20d: bool = True,
    use_cache: bool = True,
) -> Dict[str, SymbolSnapshot]:
    """Build canonical snapshots for multiple tickers. Uses batched delayed fetch then core per ticker."""
    from app.core.data.orats_client import fetch_full_equity_snapshots
    from app.core.orats.orats_core_client import fetch_core_snapshot, derive_avg_stock_volume_20d as _derive_avg
    from app.core.config.orats_secrets import ORATS_API_TOKEN

    if not tickers:
        return {}

    syms = [str(t).strip().upper() for t in tickers if str(t).strip()]
    now_iso = datetime.now(timezone.utc).isoformat()
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    token = (ORATS_API_TOKEN or "").strip()

    # Batch delayed quote + iv_rank
    try:
        full_map = fetch_full_equity_snapshots(syms)
    except Exception as e:
        logger.warning("[SYMBOL_SNAPSHOT] batch delayed quote failed: %s", e)
        full_map = {}

    results: Dict[str, SymbolSnapshot] = {}
    for sym in syms:
        snapshot = SymbolSnapshot(ticker=sym)
        delayed = full_map.get(sym)

        if delayed:
            snapshot.price = _coerce_float(getattr(delayed, "price", None))
            snapshot.bid = _coerce_float(getattr(delayed, "bid", None))
            snapshot.ask = _coerce_float(getattr(delayed, "ask", None))
            snapshot.volume = _coerce_int(getattr(delayed, "volume", None))
            snapshot.quote_date = getattr(delayed, "quote_date", None) or None
            snapshot.iv_rank = _coerce_float(getattr(delayed, "iv_rank", None))
            snapshot.quote_as_of = snapshot.quote_date or now_iso
            for f in ("price", "bid", "ask", "volume", "quote_date", "iv_rank"):
                if getattr(snapshot, f) is not None:
                    snapshot.field_sources[f] = "delayed_strikes_ivrank"
            if snapshot.price is None:
                snapshot.missing_reasons["price"] = "Not provided by ORATS delayed quote"
            if snapshot.volume is None:
                snapshot.missing_reasons["volume"] = "Not provided by ORATS delayed quote"
            if snapshot.quote_date is None:
                snapshot.missing_reasons["quote_date"] = "Not provided by ORATS delayed quote"
            if snapshot.iv_rank is None:
                snapshot.missing_reasons["iv_rank"] = "Not provided by ORATS delayed quote"
        else:
            for f in ("price", "bid", "ask", "volume", "quote_date", "iv_rank"):
                snapshot.missing_reasons[f] = "Delayed quote fetch failed or empty"
            snapshot.quote_as_of = now_iso

        # Core per ticker
        cache_key_core = _cache_key(sym, _CACHE_KEY_CORE, date_key)
        if use_cache and cache_key_core in _snapshot_cache:
            core_row = _snapshot_cache[cache_key_core]
        else:
            core_row = None
            if token:
                try:
                    core_row = fetch_core_snapshot(sym, ["ticker", "stkVolu", "avgOptVolu20d"], token)
                    if use_cache:
                        _snapshot_cache[cache_key_core] = core_row
                except Exception as e:
                    logger.debug("[SYMBOL_SNAPSHOT] %s core fetch failed: %s", sym, e)
            if core_row is not None:
                snapshot.stock_volume_today = _coerce_int(core_row.get("stkVolu"))
                snapshot.avg_option_volume_20d = _coerce_float(core_row.get("avgOptVolu20d"))
                if snapshot.stock_volume_today is not None:
                    snapshot.field_sources["stock_volume_today"] = "datav2/cores"
                if snapshot.avg_option_volume_20d is not None:
                    snapshot.field_sources["avg_option_volume_20d"] = "datav2/cores"
            snapshot.core_as_of = now_iso
            if snapshot.stock_volume_today is None:
                snapshot.missing_reasons["stock_volume_today"] = "Not provided by ORATS Core Data"
            if snapshot.avg_option_volume_20d is None:
                snapshot.missing_reasons["avg_option_volume_20d"] = "Not provided by ORATS Core Data"

        # Optional derived
        if derive_avg_stock_volume_20d and token:
            cache_key_derived = _cache_key(sym, _CACHE_KEY_DERIVED, date_key)
            if use_cache and cache_key_derived in _snapshot_cache:
                snapshot.avg_stock_volume_20d = _snapshot_cache[cache_key_derived]
                if snapshot.avg_stock_volume_20d is not None:
                    snapshot.field_sources["avg_stock_volume_20d"] = "DERIVED_ORATS_HIST"
            else:
                try:
                    avg = _derive_avg(sym, token, trade_date=snapshot.quote_date or None)
                    if use_cache:
                        _snapshot_cache[cache_key_derived] = avg
                    if avg is not None:
                        snapshot.avg_stock_volume_20d = avg
                        snapshot.field_sources["avg_stock_volume_20d"] = "DERIVED_ORATS_HIST"
                    else:
                        snapshot.missing_reasons["avg_stock_volume_20d"] = "Derived from hist/dailies failed or insufficient data"
                except Exception as e:
                    snapshot.missing_reasons["avg_stock_volume_20d"] = f"Derived calculation failed: {e}"
            snapshot.derived_as_of = now_iso

        # Per-symbol snapshot summary (TASK D)
        endpoints_called = []
        if delayed is not None:
            endpoints_called.append("delayed_strikes_ivrank")
        if core_row is not None:
            endpoints_called.append("datav2/cores")
        if snapshot.field_sources.get("avg_stock_volume_20d"):
            endpoints_called.append("datav2/hist/dailies")
        fields_present = [f for f in ("price", "bid", "ask", "volume", "quote_date", "iv_rank", "stock_volume_today", "avg_option_volume_20d", "avg_stock_volume_20d") if getattr(snapshot, f, None) is not None]
        logger.debug(
            "[SYMBOL_SNAPSHOT] %s endpoints=%s quote_as_of=%s core_as_of=%s derived_as_of=%s fields_present=%s",
            sym, endpoints_called, snapshot.quote_as_of, snapshot.core_as_of, snapshot.derived_as_of, fields_present,
        )
        results[sym] = snapshot

    return results


def clear_snapshot_cache() -> None:
    """Clear per-run cache (e.g. between tests or runs)."""
    global _snapshot_cache
    _snapshot_cache.clear()
