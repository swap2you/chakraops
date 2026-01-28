# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Theta options diagnostics for dashboard and health checks (no trading logic).

This module runs direct HTTP calls to Theta v3 endpoints to validate data availability.
It does NOT use provider abstractions, does NOT apply trading filters, and does NOT
write to the DB or affect trading / eligibility logic.

Diagnostics validate Theta DATA AVAILABILITY, not tradability.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import pytz

from app.core.market_time import get_market_state
from app.data.theta_v3_routes import stock_url, index_url, build_headers

logger = logging.getLogger(__name__)


@dataclass
class ThetaDiagnosticResult:
    now_utc: str
    now_et: str
    market_state: str
    is_market_open: bool
    # Separate availability flags for each namespace
    stock_available: bool = False
    option_available: bool = False
    index_available: Optional[bool] = None
    # Option-specific details (primary focus)
    theta_expirations_ok: bool = False
    expirations_count: int = 0
    first_expiration: Optional[str] = None
    theta_chain_ok: bool = False
    contracts_count: int = 0
    sample_contract: Optional[Dict[str, Any]] = None
    latency_ms_expirations: Optional[float] = None
    latency_ms_chain: Optional[float] = None
    # Stock/index test results (if tested)
    stock_error: Optional[str] = None
    stock_error_type: Optional[str] = None
    index_error: Optional[str] = None
    index_error_type: Optional[str] = None
    # Overall error (if any)
    error: Optional[str] = None
    error_type: Optional[str] = None


def _now_utc_and_et() -> tuple[datetime, datetime]:
    """Return (now_utc, now_et) as timezone-aware datetimes."""
    utc = pytz.UTC
    et_tz = pytz.timezone("America/New_York")
    now_utc = datetime.now(utc)
    now_et = now_utc.astimezone(et_tz)
    return now_utc, now_et


def run_theta_diagnostic(symbol: str = "SPY") -> Dict[str, Any]:
    """Run a Theta connectivity diagnostic for stock, option, and index namespaces.
    
    IMPORTANT: Diagnostics validate Theta DATA AVAILABILITY, not tradability.
    - Zero bid/ask values are VALID per OpenAPI v3
    - Nullable fields (delta, iv) are VALID
    - A contract is valid if snapshot quote endpoint returns HTTP 200
    - Do NOT apply trading filters (bid > 0, delta ranges, etc.) in diagnostics
    
    Returns a dict with:
    - now_utc, now_et (ISO strings)
    - market_state, is_market_open
    - stock_available, option_available, index_available (separate flags)
    - Option details: theta_expirations_ok, expirations_count, first_expiration,
      theta_chain_ok, contracts_count, sample_contract
    - Latencies: latency_ms_expirations, latency_ms_chain
    - Errors: stock_error/stock_error_type, index_error/index_error_type, error/error_type
    """
    import httpx
    
    now_utc, now_et = _now_utc_and_et()
    market_state = get_market_state(now_et)
    is_open = market_state == "OPEN"

    result = ThetaDiagnosticResult(
        now_utc=now_utc.isoformat(),
        now_et=now_et.isoformat(),
        market_state=market_state,
        is_market_open=is_open,
        stock_available=False,
        option_available=False,
        index_available=None,
        theta_expirations_ok=False,
        expirations_count=0,
        first_expiration=None,
        theta_chain_ok=False,
        contracts_count=0,
        sample_contract=None,
        latency_ms_expirations=None,
        latency_ms_chain=None,
        stock_error=None,
        stock_error_type=None,
        index_error=None,
        index_error_type=None,
        error=None,
        error_type=None,
    )
    
    headers = build_headers()
    
    # Test stock availability (403 = plan limitation, not failure)
    try:
        stock_test_url = stock_url("/snapshot/trade")
        stock_test_params = {"symbol": "AAPL", "format": "json"}
        with httpx.Client(timeout=5.0) as client:
            r_stock = client.get(stock_test_url, params=stock_test_params, headers=headers)
            if r_stock.status_code == 200:
                result.stock_available = True
            elif r_stock.status_code == 403:
                result.stock_available = False
                result.stock_error = "Blocked by subscription tier"
                result.stock_error_type = "PLAN_LIMITATION"
                logger.info("[THETA][DIAG] Stock snapshot blocked by plan (403)")
            else:
                result.stock_available = False
                result.stock_error = f"HTTP {r_stock.status_code}"
                result.stock_error_type = "HTTP_ERROR"
    except Exception as e:
        result.stock_available = False
        result.stock_error = str(e)
        result.stock_error_type = type(e).__name__
        logger.debug("[THETA][DIAG] Stock test failed: %s", e)

    # Step 1: Get expirations (direct HTTP call, NO provider dependency)
    from app.data.theta_v3_routes import option_url
    
    try:
        t0 = time.monotonic()
        expirations_url = option_url("/list/expirations")
        expirations_params = {"symbol": symbol.upper(), "format": "json"}
        with httpx.Client(timeout=5.0) as client:
            r_exp = client.get(expirations_url, params=expirations_params, headers=headers)
            t1 = time.monotonic()
            result.latency_ms_expirations = (t1 - t0) * 1000.0
            
            if r_exp.status_code != 200:
                result.error = f"Expirations HTTP {r_exp.status_code}"
                result.error_type = "NO_EXPIRATIONS"
                return asdict(result)
            
            # Parse expirations response: {"response":[{"symbol":"SPY","expiration":"YYYY-MM-DD"}, ...]}
            expirations_data = r_exp.json()
            expirations_list = []
            if isinstance(expirations_data, dict) and "response" in expirations_data:
                expirations_list = expirations_data["response"]
            elif isinstance(expirations_data, list):
                expirations_list = expirations_data
            
            if not expirations_list:
                result.error = "No expirations in response"
                result.error_type = "NO_EXPIRATIONS"
                return asdict(result)
            
            # Extract expiration strings from response
            expiration_strings = []
            for exp_item in expirations_list:
                if isinstance(exp_item, dict):
                    exp_str = exp_item.get("expiration") or exp_item.get("date") or exp_item.get("expiry")
                elif isinstance(exp_item, str):
                    exp_str = exp_item
                else:
                    continue
                if exp_str:
                    expiration_strings.append(exp_str)
            
            if not expiration_strings:
                result.error = "Could not extract expiration strings from response"
                result.error_type = "NO_EXPIRATIONS"
                return asdict(result)
            
            result.theta_expirations_ok = True
            result.expirations_count = len(expiration_strings)
            
    except Exception as e:
        result.error = str(e)
        result.error_type = "NO_EXPIRATIONS"
        logger.warning("[THETA][DIAG] Expirations probe failed for %s: %s", symbol, e)
        return asdict(result)
    
    # Step 2: Normalize, sort, and select expiration
    # Expirations are returned as strings in "YYYY-MM-DD" format
    # Prefer nearest future expiration, fallback to latest historical
    from datetime import date
    
    today = date.today()
    
    parsed_exps = []
    for exp in expiration_strings:
        try:
            y, m, d = map(int, exp.split("-"))
            parsed_exps.append(date(y, m, d))
        except Exception:
            continue
    
    if not parsed_exps:
        raise RuntimeError("NO_VALID_EXPIRATIONS")
    
    # Prefer nearest future expiration
    future_exps = sorted([e for e in parsed_exps if e >= today])
    
    if future_exps:
        selected_exp = future_exps[0]
        logger.info("[THETA][DIAG] Selected nearest future expiration: %s", selected_exp.isoformat())
    else:
        # Fallback to latest historical expiration
        selected_exp = max(parsed_exps)
        logger.info("[THETA][DIAG] No future expirations, using latest historical: %s", selected_exp.isoformat())
    
    expiration_ymd = selected_exp.strftime("%Y%m%d")
    expiration_iso = selected_exp.isoformat()
    
    result.first_expiration = expiration_iso
    expiration = expiration_ymd
    expiration_raw = expiration_iso
    
    logger.info("[THETA][DIAG] Using expiration YYYYMMDD=%s (raw=%s)", expiration, expiration_raw)
    
    # Step 3: Get strikes (direct HTTP call, NO provider dependency)
    strikes_count = 0
    strikes_tested = 0
    snapshot_success_count = 0
    
    try:
        t0 = time.monotonic()
        strikes_url = option_url("/list/strikes")
        strikes_params = {"symbol": symbol.upper(), "expiration": expiration, "format": "json"}
        with httpx.Client(timeout=5.0) as client:
            r_strikes = client.get(strikes_url, params=strikes_params, headers=headers)
            t1 = time.monotonic()
            result.latency_ms_chain = (t1 - t0) * 1000.0
            
            if r_strikes.status_code != 200:
                result.error = f"Strikes HTTP {r_strikes.status_code}"
                result.error_type = "NO_STRIKES"
                return asdict(result)
            
            # Parse strikes response
            strikes_data = r_strikes.json()
            raw_strikes = []
            if isinstance(strikes_data, list):
                raw_strikes = strikes_data
            elif isinstance(strikes_data, dict):
                raw_strikes = strikes_data.get("strikes") or strikes_data.get("response") or []
            
            # Normalize strikes immediately after fetching them
            # Theta v3 returns objects like {"symbol": "SPY", "strike": 120.0} or direct floats
            normalized_strikes = []
            for s in raw_strikes:
                if isinstance(s, dict) and "strike" in s:
                    normalized_strikes.append(float(s["strike"]))
                elif isinstance(s, (int, float)):
                    normalized_strikes.append(float(s))
                else:
                    logger.warning(f"[THETA][DIAG] Skipping unknown strike format: {s}")
            
            strikes = normalized_strikes
            strikes_count = len(strikes)
            result.contracts_count = strikes_count  # Store strikes count
            
            if strikes_count == 0:
                result.error = "No strikes in response"
                result.error_type = "NO_STRIKES"
                return asdict(result)
            
            # Step 4: SNAPSHOT LOOP (MUST RUN - no early returns above this point)
            # FORCE strikes to a concrete list (prevents generator/lazy iterator failures)
            strike_list = list(strikes)
            
            # Hard diagnostic logging BEFORE the snapshot loop (mandatory)
            logger.info(f"[THETA][DIAG] strikes runtime type={type(strikes)}")
            logger.info(f"[THETA][DIAG] strikes repr={repr(strikes)}")
            logger.info(f"[THETA][DIAG] strikes truthy={bool(strikes)}")
            logger.info(f"[THETA][DIAG] strikes len={len(strikes) if hasattr(strikes, '__len__') else 'NA'}")
            logger.info(f"[THETA][DIAG] strike_list type={type(strike_list)}")
            logger.info(f"[THETA][DIAG] strike_list len={len(strike_list)}")
            logger.info(f"[THETA][DIAG] strike_list[:5]={strike_list[:5]}")
            
            # Test up to 5 strikes, accept ANY HTTP 200 response
            for strike_val in strike_list[:5]:
                # Execution marker INSIDE the loop (first line)
                logger.info("[THETA][DIAG] ENTERED SNAPSHOT LOOP")
                
                try:
                    strike_f = float(strike_val)
                except (TypeError, ValueError) as e:
                    logger.warning(f"[THETA][DIAG] Skipping invalid strike value: {strike_val} ({e})")
                    continue
                
                # Explicitly increment BEFORE snapshot call
                strikes_tested += 1
                logger.debug(f"[THETA][DIAG] Testing strike {strike_f} (strikes_tested={strikes_tested})")
                
                snapshot_url = option_url("/snapshot/quote")
                snapshot_params = {
                    "symbol": symbol.upper(),
                    "expiration": expiration,
                    "strike": strike_f,
                    "right": "C",  # Use calls for diagnostics
                    "format": "json",
                }
                
                try:
                    r_snap = client.get(snapshot_url, params=snapshot_params, headers=headers, timeout=5.0)
                except Exception as e:
                    raise RuntimeError(f"[THETA][DIAG] SNAPSHOT EXCEPTION: {e}") from e
                
                # Explicitly increment on HTTP 200
                if r_snap.status_code == 200:
                    snapshot_success_count += 1
                    logger.debug(f"[THETA][DIAG] Snapshot HTTP 200 for strike {strike_f}")
                    try:
                        snap_data = r_snap.json()
                        if isinstance(snap_data, dict) and result.sample_contract is None:
                            # Use first successful snapshot as sample (even if bid/ask = 0)
                            result.sample_contract = {
                                "expiry": expiration_raw,
                                "strike": strike_f,
                                "right": "C",
                                "bid": snap_data.get("bid") or snap_data.get("bid_price"),
                                "ask": snap_data.get("ask") or snap_data.get("ask_price"),
                                "delta": snap_data.get("delta"),
                                "iv": snap_data.get("implied_vol") or snap_data.get("iv") or snap_data.get("implied_volatility"),
                                "open_interest": snap_data.get("open_interest") or snap_data.get("oi"),
                            }
                    except Exception as e:
                        raise RuntimeError(f"[THETA][DIAG] SNAPSHOT EXCEPTION: Failed to parse snapshot JSON: {e}") from e
                    # Break after first success (per pseudocode)
                    break
                else:
                    logger.debug(f"[THETA][DIAG] Snapshot HTTP {r_snap.status_code} for strike {strike_f}")
            
            # Enforce hard invariant AFTER the loop
            if strikes_count > 0 and strikes_tested == 0:
                raise RuntimeError(
                    f"[THETA][DIAG] INVARIANT VIOLATION: strikes_count={strikes_count} "
                    f"but snapshot loop never executed"
                )
            
            # Success criteria: ONE snapshot HTTP 200 = PASS
            # Data values can be zero or null - this is diagnostics, not trading
            if snapshot_success_count >= 1:
                result.option_available = True
                result.theta_chain_ok = True
                result.contracts_count = snapshot_success_count
            else:
                result.option_available = False
                result.error = f"Snapshot unavailable: strikes_count={strikes_count} strikes_tested={strikes_tested} snapshot_success={snapshot_success_count}"
                result.error_type = "SNAPSHOT_UNAVAILABLE"
            
            # Log ONCE: strikes_count, strikes_tested, snapshot_success
            logger.info(
                "[THETA][DIAG] strikes_count=%d strikes_tested=%d snapshot_success=%d",
                strikes_count, strikes_tested, snapshot_success_count
            )
            
    except RuntimeError as e:
        # Re-raise the hard assert
        raise
    except Exception as e:
        result.option_available = False
        result.error = str(e)
        result.error_type = type(e).__name__
        logger.warning("[THETA][DIAG] Strikes/snapshot probe failed for %s: %s", symbol, e)
    
    # Test index availability (optional, may be skipped if not needed)
    try:
        index_test_url = index_url("/snapshot/quote")
        index_test_params = {"symbol": "SPX", "format": "json"}
        with httpx.Client(timeout=5.0) as client:
            r_index = client.get(index_test_url, params=index_test_params, headers=headers)
            if r_index.status_code == 200:
                result.index_available = True
            elif r_index.status_code == 403:
                result.index_available = False
                result.index_error = "Blocked by subscription tier"
                result.index_error_type = "PLAN_LIMITATION"
                logger.info("[THETA][DIAG] Index snapshot blocked by plan (403)")
            else:
                result.index_available = False
                result.index_error = f"HTTP {r_index.status_code}"
                result.index_error_type = "HTTP_ERROR"
    except Exception as e:
        result.index_available = False
        result.index_error = str(e)
        result.index_error_type = type(e).__name__
        logger.debug("[THETA][DIAG] Index test failed: %s", e)

    logger.info(
        "[THETA][DIAG] PASS symbol=%s stock=%s option=%s index=%s exp_ok=%s chain_ok=%s "
        "exp_count=%d chain_count=%d lat_ms_exp=%.1f lat_ms_chain=%.1f",
        symbol,
        result.stock_available,
        result.option_available,
        result.index_available,
        result.theta_expirations_ok,
        result.theta_chain_ok,
        result.expirations_count,
        result.contracts_count,
        result.latency_ms_expirations or -1.0,
        result.latency_ms_chain or -1.0,
    )
    return asdict(result)


__all__ = ["run_theta_diagnostic"]

