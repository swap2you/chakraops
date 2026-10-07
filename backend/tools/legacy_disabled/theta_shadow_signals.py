#!/usr/bin/env python3
"""
Theta-derived shadow signals for realtime regime (display-only).

Reuses REST/CSV logic from tools/thetadata_capabilities. No DB writes.
Returns price_trend, volatility, liquidity for use by get_shadow_realtime_regime.
Short timeout; defensive; any exception -> unavailable + note.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

# Reuse Theta REST plumbing from capabilities (avoid duplicate HTTP logic)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from tools.thetadata_capabilities import (
    BASE_URL,
    TIMEOUT,
    _req_csv,
    _parse_csv,
    _pick,
    _header_or_default,
    _next_friday_yyyymmdd,
)

_SHADOW_TIMEOUT = min(10.0, TIMEOUT)
_PRICE_TREND_THRESHOLD = 0.003  # 0.30%
_IV_HIGH = 0.25
_IV_LOW = 0.15
_VOL_NORMAL = 500
_VOL_MIXED = 100


def get_theta_shadow_signals(symbol: str = "SPY") -> dict[str, Any]:
    """
    Fetch minimal Theta-derived signals for shadow realtime regime.

    Returns dict with:
      - price_trend: "bullish"|"neutral"|"bearish"|"unavailable"
      - volatility: "low"|"moderate"|"high"|"unavailable"
      - liquidity: "normal"|"mixed"|"thin"|"unavailable"
      - notes: list of strings

    Uses stock last vs previous close for trend; IV from greeks for volatility;
    option OHLC volume for liquidity. On any exception, sets that signal to
    unavailable and adds a note. No DB writes.
    """
    out: dict[str, Any] = {
        "price_trend": "unavailable",
        "volatility": "unavailable",
        "liquidity": "unavailable",
        "notes": [],
    }

    def _note(msg: str) -> None:
        out["notes"].append(msg)

    try:
        with httpx.Client(base_url=BASE_URL, timeout=_SHADOW_TIMEOUT) as client:
            # --- price_trend: last vs previous close ---
            last_price: float | None = None
            ref_price: float | None = None
            try:
                text = _req_csv(client, "/stock/snapshot/trade", {"symbol": symbol})
                rows = _parse_csv(text)
                if rows:
                    header, data_start = _header_or_default(rows, ["ms_of_day", "price", "date"])
                    for row in rows[data_start:]:
                        if not row:
                            continue
                        pcl = _pick(row, header, "price", "close", "last")
                        last_price = pcl[0] or pcl[1] or pcl[2]
                        if last_price is None and len(row) >= 2:
                            try:
                                last_price = float(row[1])
                            except (ValueError, TypeError):
                                pass
                        break
            except Exception as e:
                _note(f"price_trend: stock trade failed ({e})")
            if last_price is None:
                try:
                    today_str = date.today().strftime("%Y%m%d")
                    text = _req_csv(client, "/stock/history/eod", {"symbol": symbol, "start_date": today_str, "end_date": today_str})
                    rows = _parse_csv(text)
                    if rows:
                        header, data_start = _header_or_default(rows, ["open", "high", "low", "close", "volume", "date"])
                        for row in rows[data_start:]:
                            if not row:
                                continue
                            v = _pick(row, header, "close")[0]
                            if v is not None:
                                last_price = float(v)
                            break
                except Exception as e:
                    _note(f"price_trend: eod today failed ({e})")
            if last_price is not None and ref_price is None:
                try:
                    yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
                    text = _req_csv(client, "/stock/history/eod", {"symbol": symbol, "start_date": yesterday, "end_date": yesterday})
                    rows = _parse_csv(text)
                    if rows:
                        header, data_start = _header_or_default(rows, ["close"])
                        for row in rows[data_start:]:
                            if not row:
                                continue
                            v = _pick(row, header, "close")[0]
                            if v is not None and float(v) > 0:
                                ref_price = float(v)
                            break
                except Exception as e:
                    _note(f"price_trend: ref (previous close) failed ({e})")
            if last_price is not None and ref_price is not None and ref_price > 0:
                return_pct = (last_price - ref_price) / ref_price
                if return_pct >= _PRICE_TREND_THRESHOLD:
                    out["price_trend"] = "bullish"
                elif return_pct <= -_PRICE_TREND_THRESHOLD:
                    out["price_trend"] = "bearish"
                else:
                    out["price_trend"] = "neutral"
            elif last_price is not None:
                _note("price_trend: ref missing")
            else:
                _note("price_trend: last price missing")

            # --- volatility: IV from greeks ---
            try:
                exp_yyyymmdd = _next_friday_yyyymmdd()
                for path in ["/bulk_snapshot/option/greeks", "/option/bulk_snapshot/greeks"]:
                    try:
                        text = _req_csv(client, path, {"symbol": symbol, "exp": exp_yyyymmdd})
                        rows = _parse_csv(text)
                        if not rows:
                            continue
                        header, data_start = _header_or_default(rows, ["implied_vol", "iv", "delta", "theta", "vega"])
                        for row in rows[data_start:]:
                            if not row:
                                continue
                            iv = _pick(row, header, "implied_vol", "iv")[0] or _pick(row, header, "implied_vol", "iv")[1]
                            if iv is not None:
                                iv_f = float(iv)
                                if iv_f >= _IV_HIGH:
                                    out["volatility"] = "high"
                                elif iv_f <= _IV_LOW:
                                    out["volatility"] = "low"
                                else:
                                    out["volatility"] = "moderate"
                            break
                        if out["volatility"] != "unavailable":
                            break
                    except Exception:
                        continue
                if out["volatility"] == "unavailable":
                    _note("volatility: iv missing")
            except Exception as e:
                _note(f"volatility: greeks failed ({e})")

            # --- liquidity: option OHLC volume ---
            try:
                exp_yyyymmdd = _next_friday_yyyymmdd()
                strike = 50000 if symbol.upper() == "SPY" else 40000
                for path in ["/option/snapshot/ohlc", "/option/bulk_snapshot/ohlc", "/bulk_snapshot/option/ohlc"]:
                    try:
                        params: dict[str, Any] = {"symbol": symbol, "exp": exp_yyyymmdd, "right": "C", "strike": strike}
                        if "bulk" in path:
                            params = {"symbol": symbol, "exp": exp_yyyymmdd}
                        text = _req_csv(client, path, params)
                        rows = _parse_csv(text)
                        if not rows:
                            continue
                        header, data_start = _header_or_default(rows, ["volume", "close", "date"])
                        for row in rows[data_start:]:
                            if not row:
                                continue
                            vol = _pick(row, header, "volume")[0]
                            if vol is not None:
                                try:
                                    v = int(float(vol))
                                    if v >= _VOL_NORMAL:
                                        out["liquidity"] = "normal"
                                    elif v >= _VOL_MIXED:
                                        out["liquidity"] = "mixed"
                                    else:
                                        out["liquidity"] = "thin"
                                except (ValueError, TypeError):
                                    pass
                            break
                        if out["liquidity"] != "unavailable":
                            break
                    except Exception:
                        continue
                if out["liquidity"] == "unavailable":
                    _note("liquidity: volume missing")
            except Exception as e:
                _note(f"liquidity: option ohlc failed ({e})")

    except Exception as e:
        out["notes"].append(str(e))
    return out
