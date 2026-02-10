# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Single EquitySnapshot model — used by Universe, Ticker, Evaluation, Decision artifacts.

Phase 8C: Built from ORATS Core Data v2 (/datav2/cores) only. No UNKNOWN without documented reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.data.orats_field_map import (
    INFORMATIONAL_CANONICAL_FIELDS,
    OPTIONAL_CANONICAL_FIELDS,
    ORATS_TO_CANONICAL,
    REQUIRED_CANONICAL_FIELDS,
    orats_to_canonical,
)

# ORATS /cores field names to request for a full equity snapshot (inverse of map for cores)
DEFAULT_CORES_ORATS_FIELDS = [
    "stkVolu",
    "avgOptVolu20d",
    "ivPctile1y",
    "ivRank",
    "ivRank1m",
    "ivPct1m",
    "pxCls",
    "priorCls",
    "tradeDate",
    "confidence",
    "sector",
    "marketCap",
    "industry",
]


@dataclass
class EquitySnapshot:
    """
    Canonical per-ticker snapshot. All fields from ORATS Core or explicitly derived/missing.
    Universe row == Ticker snapshot == Decision artifact (same run).
    """
    ticker: str
    trade_date: Optional[str] = None
    last_close_price: Optional[float] = None
    stock_volume_today: Optional[int] = None
    avg_option_volume_20d: Optional[float] = None
    iv_rank: Optional[float] = None
    iv_percentile_1y: Optional[float] = None
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    industry: Optional[str] = None
    prior_close: Optional[float] = None
    orats_confidence: Optional[float] = None
    # Optional derived (Phase 8D); only when enabled from hist/dailies
    avg_stock_volume_20d: Optional[float] = None
    source: str = "ORATS_CORE"
    missing_fields: List[str] = field(default_factory=list)
    missing_reasons: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """For API/UI serialization; no UNKNOWN — use null and missing_fields."""
        return {
            "ticker": self.ticker,
            "trade_date": self.trade_date,
            "last_close_price": self.last_close_price,
            "stock_volume_today": self.stock_volume_today,
            "avg_option_volume_20d": self.avg_option_volume_20d,
            "iv_rank": self.iv_rank,
            "iv_percentile_1y": self.iv_percentile_1y,
            "sector": self.sector,
            "market_cap": self.market_cap,
            "industry": self.industry,
            "prior_close": self.prior_close,
            "orats_confidence": self.orats_confidence,
            "avg_stock_volume_20d": self.avg_stock_volume_20d,
            "source": self.source,
            "missing_fields": self.missing_fields.copy(),
            "missing_reasons": self.missing_reasons.copy(),
        }


REASON_NOT_PROVIDED = "Not provided by ORATS Core Data"


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


def build_equity_snapshot_from_core(
    ticker: str,
    token: str,
    orats_fields: Optional[List[str]] = None,
    timeout_sec: float = 15.0,
    derive_avg_stock_volume_20d: bool = False,
) -> EquitySnapshot:
    """
    Fetch /datav2/cores for ticker and build EquitySnapshot. No silent defaults.
    If ORATS does not return a field → add to missing_fields with reason.
    """
    from app.core.orats.orats_core_client import fetch_core_snapshot, OratsCoreError

    fields_to_request = orats_fields or DEFAULT_CORES_ORATS_FIELDS
    snapshot = EquitySnapshot(ticker=ticker.upper(), source="ORATS_CORE")

    try:
        raw = fetch_core_snapshot(ticker, fields_to_request, token, timeout_sec=timeout_sec)
    except OratsCoreError as e:
        snapshot.missing_fields = list(REQUIRED_CANONICAL_FIELDS) + list(OPTIONAL_CANONICAL_FIELDS)
        snapshot.missing_reasons = {f: f"ORATS cores request failed: {e}" for f in snapshot.missing_fields}
        return snapshot

    mapped = orats_to_canonical(raw)

    # Populate from mapped (canonical names only); coerce types
    snapshot.trade_date = str(mapped["trade_date"]) if mapped.get("trade_date") is not None else None
    snapshot.last_close_price = _coerce_float(mapped.get("last_close_price"))
    snapshot.stock_volume_today = _coerce_int(mapped.get("stock_volume_today"))
    snapshot.avg_option_volume_20d = _coerce_float(mapped.get("avg_option_volume_20d"))
    snapshot.iv_rank = _coerce_float(mapped.get("iv_rank"))
    snapshot.iv_percentile_1y = _coerce_float(mapped.get("iv_percentile_1y"))
    snapshot.sector = str(mapped["sector"]) if mapped.get("sector") is not None else None
    snapshot.market_cap = _coerce_float(mapped.get("market_cap"))
    snapshot.industry = str(mapped["industry"]) if mapped.get("industry") is not None else None
    snapshot.prior_close = _coerce_float(mapped.get("prior_close"))
    snapshot.orats_confidence = _coerce_float(mapped.get("orats_confidence"))

    # Required: ticker always set; others missing → list with reason
    for name in REQUIRED_CANONICAL_FIELDS:
        if name == "ticker":
            continue
        val = getattr(snapshot, name, None)
        if val is None:
            snapshot.missing_fields.append(name)
            snapshot.missing_reasons[name] = REASON_NOT_PROVIDED

    # Optional: record reason only when missing (do not block)
    for name in OPTIONAL_CANONICAL_FIELDS:
        val = getattr(snapshot, name, None)
        if val is None:
            snapshot.missing_reasons[name] = REASON_NOT_PROVIDED

    # Phase 8D: derived avg_stock_volume_20d from /datav2/hist/dailies when enabled
    if derive_avg_stock_volume_20d:
        try:
            from app.core.orats.orats_core_client import derive_avg_stock_volume_20d as _derive_avg
            avg = _derive_avg(ticker, token, trade_date=snapshot.trade_date, timeout_sec=timeout_sec)
            if avg is not None:
                snapshot.avg_stock_volume_20d = avg
                snapshot.missing_reasons.pop("avg_stock_volume_20d", None)
                if "avg_stock_volume_20d" in snapshot.missing_fields:
                    snapshot.missing_fields = [f for f in snapshot.missing_fields if f != "avg_stock_volume_20d"]
        except Exception:
            pass  # Do not block; warning only (already in missing_reasons if missing)

    return snapshot
