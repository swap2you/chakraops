# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS Option Chain Pipeline - Two-Step Architecture.

This module implements the correct ORATS integration:

STEP 1: Discover option chain via /datav2/strikes
  - Input: underlying ticker (e.g., AAPL)
  - Output: list of (expirDate, strike, optionType) tuples

STEP 2: Enrich with liquidity via /datav2/strikes/options (non-derived only)
  - Input: OCC option symbols (e.g., AAPL260320C00175000) via tickers= param
  - Output: bid, ask, volume, openInterest, greeks

OCC Symbol Format (no space padding; must match request and response for merge):
  - ROOT + YYMMDD + C/P + STRIKE*1000 (8 digits). Example: SPY260320P00691000

Data Modes:
  - delayed: https://api.orats.io/datav2 (15-min delay, includes OPRA fields)
  - live: https://api.orats.io/datav2/live (real-time, includes OPRA fields)
  - live_derived: https://api.orats.io/datav2/live/derived (NO OPRA fields - will fail)

Set ORATS_DATA_MODE env var to control which mode is used.
"""

from __future__ import annotations

import logging
import os
import time
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.core.orats.endpoints import BASE_DATAV2, BASE_LIVE, PATH_STRIKES, PATH_STRIKES_OPTIONS

logger = logging.getLogger(__name__)


# ============================================================================
# ORATS Data Mode Configuration
# ============================================================================

class OratsDataMode:
    """ORATS API data mode configuration. Base URLs from app.core.orats.endpoints."""
    DELAYED = "delayed"
    LIVE = "live"
    LIVE_DERIVED = "live_derived"
    
    # Base URLs for each mode (single source: endpoints.py)
    BASE_URLS = {
        DELAYED: BASE_DATAV2,
        LIVE: BASE_LIVE,
        LIVE_DERIVED: "https://api.orats.io/datav2/live/derived",
    }
    
    @classmethod
    def get_current_mode(cls) -> str:
        """Get current data mode from environment."""
        mode = os.environ.get("ORATS_DATA_MODE", cls.DELAYED).lower()
        if mode not in cls.BASE_URLS:
            logger.warning(
                "[ORATS_CONFIG] Invalid ORATS_DATA_MODE=%s, defaulting to 'delayed'",
                mode
            )
            return cls.DELAYED
        return mode
    
    @classmethod
    def get_base_url(cls, mode: Optional[str] = None) -> str:
        """Get base URL for the specified or current mode."""
        if mode is None:
            mode = cls.get_current_mode()
        return cls.BASE_URLS.get(mode, cls.BASE_URLS[cls.DELAYED])

    @classmethod
    def mode_from_chain_source(cls, chain_source: str) -> str:
        """Map chain_source (LIVE|DELAYED) to OratsDataMode. For use when routing by market phase."""
        return cls.LIVE if (chain_source or "").upper() == "LIVE" else cls.DELAYED
    
    @classmethod
    def supports_opra_fields(cls, mode: Optional[str] = None) -> bool:
        """Check if mode supports OPRA liquidity fields (bid/ask/volume/OI)."""
        if mode is None:
            mode = cls.get_current_mode()
        # live_derived does NOT support OPRA fields
        return mode != cls.LIVE_DERIVED


# ============================================================================
# ORATS API Errors
# ============================================================================

class OratsChainError(Exception):
    """Raised when ORATS chain fetch fails."""
    
    def __init__(
        self,
        message: str,
        http_status: int = 0,
        response_snippet: str = "",
        endpoint: str = "",
    ) -> None:
        self.http_status = http_status
        self.response_snippet = (response_snippet or "")[:500]
        self.endpoint = endpoint
        super().__init__(message)


class OratsOpraModeError(OratsChainError):
    """Raised when OPRA fields are required but mode doesn't support them."""
    
    def __init__(self, mode: str) -> None:
        super().__init__(
            f"OPRA liquidity fields (bid/ask/volume/OI) unavailable in mode '{mode}'. "
            f"Set ORATS_DATA_MODE to 'delayed' or 'live' for OPRA support.",
            endpoint="strikes/options",
        )
        self.mode = mode


# ============================================================================
# API Configuration
# ============================================================================

ORATS_STRIKES = PATH_STRIKES  # Base chain discovery
ORATS_STRIKES_OPTIONS = PATH_STRIKES_OPTIONS  # Liquidity enrichment (OPRA symbols)
TIMEOUT_SEC = 15

# Rate limiting: 1000 req/min = 16.67/sec, we use 5/sec to be safe
RATE_LIMIT_CALLS_PER_SEC = 5.0

# Batch size for OPRA symbols (ORATS recommends max 10)
OPRA_BATCH_SIZE = 10

# Bounded strike selection. Stage-2 needs enough strikes for delta-range filtering
# after enrichment; delta filter must NOT be applied at /strikes (chain discovery only).
MAX_STRIKES_PER_EXPIRY = 20  # Strikes per expiration (was 5; 30 contracts too few for SPY)
MAX_EXPIRIES = 5  # Expirations in DTE window


# ============================================================================
# Data Models
# ============================================================================

@dataclass(frozen=True)
class BaseContract:
    """
    Base contract from /datav2/strikes (no liquidity data).
    """
    symbol: str  # Underlying symbol
    expiration: date
    strike: float
    option_type: str  # "CALL" or "PUT"
    dte: int
    delta: Optional[float] = None
    stock_price: Optional[float] = None
    
    @property
    def opra_symbol(self) -> str:
        """
        Build OCC option symbol for this contract (same format as ORATS /strikes/options).
        CRITICAL: Use NO space padding on root so request and response keys match.
        Format: ROOT + YYMMDD + C/P + STRIKE*1000(8)  e.g. "SPY260320P00691000"
        """
        from app.core.orats.orats_opra import build_orats_option_symbol
        root = self.symbol.upper().strip()
        exp_str = self.expiration.strftime("%Y-%m-%d")
        opt_char = "C" if self.option_type == "CALL" else "P"
        return build_orats_option_symbol(root, exp_str, opt_char, self.strike)


@dataclass
class EnrichedContract:
    """
    Fully enriched contract with liquidity data from /datav2/strikes/options.
    """
    # Base identifiers
    symbol: str
    expiration: date
    strike: float
    option_type: str  # "CALL" or "PUT"
    opra_symbol: str
    dte: int
    
    # Underlying price
    stock_price: Optional[float] = None
    
    # Liquidity fields (from enrichment)
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    
    # Greeks
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    
    # Implied volatility
    iv: Optional[float] = None
    
    # Metadata
    enriched: bool = False  # True if liquidity data was fetched
    fetched_at: Optional[str] = None
    
    @property
    def has_valid_liquidity(self) -> bool:
        """Check if contract has minimum valid liquidity data."""
        return (
            self.enriched and
            self.bid is not None and
            self.ask is not None and
            self.open_interest is not None and
            self.open_interest > 0
        )
    
    @property
    def spread(self) -> Optional[float]:
        """Compute bid-ask spread."""
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None
    
    @property
    def spread_pct(self) -> Optional[float]:
        """Compute spread as percentage of mid."""
        if self.mid and self.mid > 0 and self.spread is not None:
            return self.spread / self.mid
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "expiration": self.expiration.isoformat(),
            "strike": self.strike,
            "option_type": self.option_type,
            "opra_symbol": self.opra_symbol,
            "dte": self.dte,
            "stock_price": self.stock_price,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "iv": self.iv,
            "has_valid_liquidity": self.has_valid_liquidity,
            "spread": self.spread,
            "spread_pct": self.spread_pct,
            "enriched": self.enriched,
            "fetched_at": self.fetched_at,
        }


@dataclass
class OptionChainResult:
    """
    Complete option chain with enriched liquidity data.
    """
    symbol: str
    underlying_price: Optional[float] = None
    contracts: List[EnrichedContract] = field(default_factory=list)
    
    # Pipeline stats
    base_chain_count: int = 0
    opra_symbols_generated: int = 0
    enriched_count: int = 0
    contracts_with_liquidity: int = 0
    
    # Timing
    fetch_duration_ms: int = 0
    fetched_at: Optional[str] = None
    
    # Mode info
    data_mode: str = ""
    
    # Error tracking
    error: Optional[str] = None
    
    # Telemetry from /strikes/options (endpoint_used, counts, sample symbols)
    strikes_options_telemetry: Optional[Dict[str, Any]] = None
    # Stage-2 trace for validate_one_symbol / harness comparison (endpoints, counts, samples, delta stats)
    stage2_trace: Optional[Dict[str, Any]] = None

    @property
    def puts(self) -> List[EnrichedContract]:
        """Get all put contracts."""
        return [c for c in self.contracts if c.option_type == "PUT"]
    
    @property
    def calls(self) -> List[EnrichedContract]:
        """Get all call contracts."""
        return [c for c in self.contracts if c.option_type == "CALL"]
    
    @property
    def valid_puts(self) -> List[EnrichedContract]:
        """Get puts with valid liquidity."""
        return [c for c in self.puts if c.has_valid_liquidity]
    
    @property
    def valid_calls(self) -> List[EnrichedContract]:
        """Get calls with valid liquidity."""
        return [c for c in self.calls if c.has_valid_liquidity]
    
    @property
    def liquidity_coverage(self) -> float:
        """Percentage of contracts with valid liquidity."""
        if not self.contracts:
            return 0.0
        return len([c for c in self.contracts if c.has_valid_liquidity]) / len(self.contracts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "underlying_price": self.underlying_price,
            "base_chain_count": self.base_chain_count,
            "opra_symbols_generated": self.opra_symbols_generated,
            "enriched_count": self.enriched_count,
            "contracts_with_liquidity": self.contracts_with_liquidity,
            "total_contracts": len(self.contracts),
            "puts_count": len(self.puts),
            "calls_count": len(self.calls),
            "valid_puts_count": len(self.valid_puts),
            "valid_calls_count": len(self.valid_calls),
            "liquidity_coverage": self.liquidity_coverage,
            "fetch_duration_ms": self.fetch_duration_ms,
            "fetched_at": self.fetched_at,
            "data_mode": self.data_mode,
            "error": self.error,
        }


# ============================================================================
# Rate Limiter
# ============================================================================

class _RateLimiter:
    """Simple rate limiter for ORATS API calls."""
    
    def __init__(self, calls_per_second: float = RATE_LIMIT_CALLS_PER_SEC):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self._lock = threading.Lock()
    
    def acquire(self) -> None:
        """Wait if needed to respect rate limit."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()


_RATE_LIMITER = _RateLimiter()


# ============================================================================
# Parameter Name for /strikes/options endpoint
# ============================================================================

# CRITICAL: Per ORATS Delayed Data API docs, /datav2/strikes/options uses
# the `tickers` (PLURAL) parameter. Do NOT probe - just use the correct name.
# 
# The old capability probe has been REMOVED because:
# 1. It caused confusion and inconsistent behavior
# 2. ORATS documentation clearly specifies `tickers` (plural)
# 3. Probing adds latency and complexity
#
# NOTE: For new code, use app.core.orats.orats_opra which is the clean implementation.

def get_strikes_options_param_name() -> str:
    """
    Get the correct parameter name for strikes/options endpoint.
    
    Per ORATS Delayed Data API docs: use `tickers` (PLURAL).
    """
    return "tickers"  # Always use tickers (plural) per ORATS docs


# ============================================================================
# Helper Functions
# ============================================================================

def _get_orats_token() -> str:
    """Get ORATS API token from config."""
    from app.core.config.orats_secrets import ORATS_API_TOKEN
    return ORATS_API_TOKEN


def _redact_token(params: Dict[str, Any]) -> Dict[str, Any]:
    """Redact token from params for logging."""
    redacted = params.copy()
    if "token" in redacted:
        redacted["token"] = "***REDACTED***"
    return redacted


def _safe_float(val: Any) -> Optional[float]:
    """Safely convert to float, returning None for invalid values."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f or f == float('inf') or f == float('-inf'):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    """Safely convert to int, returning None for invalid values."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _check_opra_fields_in_response(rows: List[Dict]) -> Tuple[bool, int, int, int]:
    """
    Check presence of OPRA fields in response rows.
    
    Returns:
        Tuple of (has_opra_fields, non_null_bidask, non_null_oi, non_null_vol)
    """
    if not rows:
        return False, 0, 0, 0
    
    non_null_bidask = 0
    non_null_oi = 0
    non_null_vol = 0
    
    for row in rows:
        bid = row.get("bidPrice") or row.get("bid")
        ask = row.get("askPrice") or row.get("ask")
        oi = row.get("openInt") or row.get("openInterest") or row.get("open_interest") or row.get("oi")
        vol = row.get("volume")
        
        if bid is not None and ask is not None:
            non_null_bidask += 1
        if oi is not None and oi > 0:
            non_null_oi += 1
        if vol is not None:
            non_null_vol += 1
    
    has_opra = non_null_bidask > 0 or non_null_oi > 0
    return has_opra, non_null_bidask, non_null_oi, non_null_vol


# ============================================================================
# STEP 1: Fetch Base Chain from /datav2/strikes
# ============================================================================

def fetch_base_chain(
    symbol: str,
    dte_min: int = 7,
    dte_max: int = 60,
    max_strikes_per_expiry: int = MAX_STRIKES_PER_EXPIRY,
    max_expiries: int = MAX_EXPIRIES,
    target_moneyness_put: float = 0.85,  # 15% below for puts
    target_moneyness_call: float = 1.10,  # 10% above for calls
    chain_mode: Optional[str] = None,
    delta_lo: Optional[float] = None,
    delta_hi: Optional[float] = None,
    strategy_mode: str = "CSP",
) -> Tuple[List[BaseContract], Optional[float], Optional[str], int]:
    """
    STEP 1: Fetch base option chain from /datav2/strikes (or /datav2/live when chain_mode=LIVE).
    
    Params: ticker, dte (window). Optional delta_lo/delta_hi (e.g. 0.10, 0.45) constrain strikes
    to OTM region for Stage-2 CSP selection. Per-contract delta comes from /strikes/options.
    
    Applies bounded selection: max N strikes per expiry, max M expiries.
    
    Args:
        symbol: Underlying ticker (e.g., AAPL)
        dte_min: Minimum days to expiration
        dte_max: Maximum days to expiration
        max_strikes_per_expiry: Max strikes to select per expiration
        max_expiries: Max expirations within DTE window
        target_moneyness_put: Target moneyness for puts (e.g., 0.85 = 15% OTM)
        target_moneyness_call: Target moneyness for calls (e.g., 1.10 = 10% OTM)
        chain_mode: Override: "DELAYED" | "LIVE" (from get_chain_source()). When None, use ORATS_DATA_MODE env.
        delta_lo: Optional min |delta| for ORATS delta filter (e.g. 0.10 for wider acquisition)
        delta_hi: Optional max |delta| for ORATS delta filter (e.g. 0.45 for wider acquisition)
    
    Returns:
        Tuple of (contracts, underlying_price, error, raw_rows_count)
    """
    _RATE_LIMITER.acquire()
    if chain_mode is not None:
        mode = OratsDataMode.mode_from_chain_source(chain_mode)
    else:
        mode = OratsDataMode.get_current_mode()
    base_url = OratsDataMode.get_base_url(mode)
    token = _get_orats_token()
    
    url = f"{base_url}{ORATS_STRIKES}"
    params = {
        "token": token,
        "ticker": symbol.upper(),
        "dte": f"{dte_min},{dte_max}",
    }
    # CSP-only: do NOT pass delta to API; delta filter is for calls (strike > spot). We need all strikes
    # and then select otm_put_strikes = [s for s in strikes if s < spot]. Passing delta would exclude them.
    
    # Log request
    logger.info(
        "[ORATS_REQ] base=%s path=%s mode=%s params=%s",
        base_url, ORATS_STRIKES, mode, _redact_token(params)
    )
    
    t0 = time.perf_counter()
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning(
            "[ORATS_RESP] status=ERROR latency_ms=%d error=%s",
            latency_ms, e
        )
        return [], None, f"Request failed: {e}", 0
    
    latency_ms = int((time.perf_counter() - t0) * 1000)
    
    if r.status_code != 200:
        logger.warning(
            "[ORATS_RESP] status=%d latency_ms=%d rows=0 has_opra_fields=false",
            r.status_code, latency_ms
        )
        return [], None, f"HTTP {r.status_code}: {r.text[:200]}", 0
    
    try:
        raw = r.json()
    except ValueError as e:
        logger.warning("[ORATS_RESP] status=%d latency_ms=%d error=invalid_json", r.status_code, latency_ms)
        return [], None, f"Invalid JSON: {e}", 0
    
    # Extract rows
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and "data" in raw:
        rows = raw.get("data", [])
    else:
        rows = []
    
    # Log response
    logger.info(
        "[ORATS_RESP] status=%d latency_ms=%d rows=%d has_opra_fields=N/A",
        r.status_code, latency_ms, len(rows)
    )
    
    # Log parse info
    if rows:
        row0_keys = list(rows[0].keys()) if rows else []
        logger.info("[ORATS_PARSE] row0_keys=%s", row0_keys)
    
    if not rows:
        return [], None, "No strikes data returned", 0
    
    # Parse rows into BaseContract objects (initially all)
    all_contracts = []
    underlying_price = None
    
    # Group by expiration for bounded selection
    expiry_strikes: Dict[date, List[Dict]] = {}
    
    for row in rows:
        try:
            exp_str = row.get("expirDate")
            if not exp_str:
                continue
            expiration = datetime.strptime(exp_str, "%Y-%m-%d").date()
            
            if expiration not in expiry_strikes:
                expiry_strikes[expiration] = []
            expiry_strikes[expiration].append(row)
            
            # Extract underlying price
            stock_price = row.get("stockPrice") or row.get("stkPx")
            if stock_price and underlying_price is None:
                underlying_price = float(stock_price)
                
        except (ValueError, TypeError):
            continue
    
    # Phase 3.4: Only CSP is implemented; CC is separate pipeline (no mixing).
    if strategy_mode != "CSP":
        return [], underlying_price, "CC_NOT_IMPLEMENTED", len(rows)

    # Sort expiries by date and take max_expiries
    sorted_expiries = sorted(expiry_strikes.keys())[:max_expiries]
    
    logger.info(
        "[ORATS_PARSE] total_expiries=%d selected_expiries=%d underlying=$%.2f strategy_mode=%s",
        len(expiry_strikes), len(sorted_expiries), underlying_price or 0, strategy_mode
    )
    
    # Near-spot CSP: OTM = strike < spot; only strikes in [spot*MIN_OTM_STRIKE_PCT, spot); take last N per expiry.
    CSP_OTM_PUT_STRIKES_PER_EXPIRY = 30
    MIN_OTM_STRIKE_PCT = 0.80

    for expiration in sorted_expiries:
        rows_for_expiry = expiry_strikes[expiration]
        strikes_all = sorted(set(float(r.get("strike", 0)) for r in rows_for_expiry))
        spot = underlying_price
        if not spot or not strikes_all:
            continue
        otm_put_strikes = [s for s in strikes_all if s < spot]
        if not otm_put_strikes:
            continue
        min_strike_floor = spot * MIN_OTM_STRIKE_PCT
        near_otm = [s for s in otm_put_strikes if s >= min_strike_floor]
        if not near_otm:
            continue
        # Last N (closest below spot)
        selected_put_strikes = sorted(near_otm)[-CSP_OTM_PUT_STRIKES_PER_EXPIRY:]
        strike_set = set(selected_put_strikes)
        # CSP: only include PUT rows from /strikes (exclude CALL rows)
        def _row_is_put(r: Dict[str, Any]) -> bool:
            ot = (r.get("optionType") or r.get("option_type") or r.get("putCall") or "").strip().upper()
            return ot in ("P", "PUT", "PUTS")
        selected_rows = [
            r for r in rows_for_expiry
            if float(r.get("strike", 0)) in strike_set and _row_is_put(r)
        ]

        for row in selected_rows:
            try:
                strike = float(row.get("strike"))
                dte = int(row.get("dte", 0))
                delta = row.get("delta")
                stock_price = row.get("stockPrice") or row.get("stkPx")
                put_delta = -float(delta) if delta is not None else None
                put_contract = BaseContract(
                    symbol=symbol.upper(),
                    expiration=expiration,
                    strike=strike,
                    option_type="PUT",
                    dte=dte,
                    delta=put_delta,
                    stock_price=float(stock_price) if stock_price else None,
                )
                all_contracts.append(put_contract)
            except (ValueError, TypeError) as e:
                logger.debug("[ORATS_PARSE] skipping row: %s", e)
                continue

    if not all_contracts:
        return [], underlying_price, "CSP_NO_OTM_STRIKES", len(rows)

    put_strikes_check = [c.strike for c in all_contracts]
    if underlying_price is not None and put_strikes_check:
        max_strike = max(put_strikes_check)
        min_strike = min(put_strikes_check)
        if max_strike >= underlying_price:
            return [], underlying_price, f"CSP assert failed: max(selected_put_strikes)={max_strike} >= spot={underlying_price}", len(rows)
        min_floor = underlying_price * MIN_OTM_STRIKE_PCT
        if min_strike < min_floor:
            return [], underlying_price, "REQUEST_SET_INVALID_CSP_STRIKE_RANGE", len(rows)

    logger.info(
        "[ORATS_PARSE] valid_contracts=%d (CSP-only OTM PUTs, %d expiries)",
        len(all_contracts), len(sorted_expiries)
    )
    return all_contracts, underlying_price, None, len(rows)


# ============================================================================
# STEP 2: Build OPRA Symbols
# ============================================================================

def build_opra_symbols(contracts: List[BaseContract]) -> Dict[str, BaseContract]:
    """
    Build OPRA symbols for each contract.
    
    Returns:
        Dict mapping OPRA symbol -> BaseContract
    """
    opra_map = {}
    for contract in contracts:
        opra = contract.opra_symbol
        opra_map[opra] = contract
    
    logger.debug("[OPRA_BUILD] Generated %d OPRA symbols", len(opra_map))
    
    return opra_map


# ============================================================================
# STEP 3: Enrich with Liquidity from /datav2/strikes/options
# ============================================================================

def _normalize_occ_symbol(s: Optional[str]) -> str:
    """Normalize OCC symbol for consistent merge key (strip, remove spaces)."""
    if not s or not isinstance(s, str):
        return ""
    return s.replace(" ", "").strip()


def _build_opra_symbol_from_row(row: Dict[str, Any]) -> Optional[str]:
    """Build OCC option symbol from API row so merge key matches BaseContract.opra_symbol."""
    from app.core.orats.orats_opra import build_orats_option_symbol
    root = (row.get("ticker") or "").strip().upper()
    exp_str = row.get("expirDate") or row.get("expiration")
    strike_raw = row.get("strike")
    opt_type = (
        row.get("optionType") or row.get("option_type") or
        row.get("putCall") or row.get("callPut") or
        row.get("put_call") or row.get("call_put") or ""
    )
    if not root or not exp_str or strike_raw is None:
        return None
    try:
        exp_str = exp_str[:10] if isinstance(exp_str, str) else str(exp_str)
        strike = float(strike_raw)
        opt_char = "C" if str(opt_type).strip().upper().startswith("C") else ("P" if str(opt_type).strip().upper().startswith("P") else None)
        if opt_char is None:
            return None
        return build_orats_option_symbol(root, exp_str, opt_char, strike)
    except (ValueError, TypeError):
        return None


def fetch_enriched_contracts(
    opra_symbols: List[str],
    batch_size: int = OPRA_BATCH_SIZE,
    require_opra_fields: bool = True,
    chain_mode: Optional[str] = None,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """
    STEP 3 (OPRA lookup): Fetch liquidity data for OCC option symbols from /datav2/strikes/options.
    Uses non-derived endpoint only (derived returns null bid/ask per ORATS docs).
    
    INVARIANT: /datav2/strikes/options MUST ONLY be called with fully-formed OCC option
    symbols. Underlying-only or mixed underlying+option calls are forbidden and will raise.
    Merge keys use normalized OCC (no space padding) so request and response match.
    
    Args:
        opra_symbols: List of OCC option symbols only (built from chain data)
        batch_size: Max symbols per request (default 10)
        require_opra_fields: If True, raise error if mode doesn't support OPRA fields
        chain_mode: Override: "DELAYED" | "LIVE". When None, use ORATS_DATA_MODE env.
    
    Returns:
        Tuple of (enrichment_map, telemetry). enrichment_map: OCC symbol -> enrichment data.
        telemetry: endpoint_used, requested_tickers_count, response_rows, non_null_bidask, non_null_oi, non_null_vol, sample_request_symbols, sample_response_optionSymbols.
        
    Raises:
        OratsChainError: If any symbol is not a valid OCC option symbol
        OratsOpraModeError: If mode is live_derived or base URL contains 'derived'
    """
    if not opra_symbols:
        return {}, _empty_telemetry()
    
    # FAIL FAST: Reject any non-OCC symbol (e.g. underlying ticker). No silent fallbacks.
    from app.core.orats.orats_opra import is_occ_option_symbol
    for s in opra_symbols:
        if not is_occ_option_symbol(s):
            raise OratsChainError(
                "strikes/options accepts OCC option symbols only; underlying ticker forbidden",
                endpoint=ORATS_STRIKES_OPTIONS,
                response_snippet=s[:80] if s else "",
            )
    
    if chain_mode is not None:
        mode = OratsDataMode.mode_from_chain_source(chain_mode)
    else:
        mode = OratsDataMode.get_current_mode()
    
    base_url = OratsDataMode.get_base_url(mode)
    # FAIL FAST: Do NOT use derived endpoint for Stage-2; derived returns null bid/ask per ORATS.
    if require_opra_fields and "derived" in base_url.lower():
        logger.error("[ORATS_OPTIONS] FAIL FAST: derived endpoint does not return OPRA bid/ask/OI")
        raise OratsOpraModeError(mode)
    if require_opra_fields and not OratsDataMode.supports_opra_fields(mode):
        logger.error(
            "[ORATS_OPTIONS] FAIL FAST: mode=%s does not support OPRA liquidity fields",
            mode
        )
        raise OratsOpraModeError(mode)
    
    token = _get_orats_token()
    param_name = get_strikes_options_param_name()
    endpoint_used = f"{base_url.rstrip('/')}{ORATS_STRIKES_OPTIONS}"
    
    enrichment_map: Dict[str, Dict[str, Any]] = {}
    total_rows = 0
    total_with_bidask = 0
    total_with_oi = 0
    total_with_vol = 0
    sample_response_option_symbols: List[str] = []
    
    # Process in batches
    for i in range(0, len(opra_symbols), batch_size):
        batch = opra_symbols[i:i + batch_size]
        
        _RATE_LIMITER.acquire()
        
        tickers_param = ",".join(batch)
        
        url = f"{base_url}{ORATS_STRIKES_OPTIONS}"
        params = {
            "token": token,
            param_name: tickers_param,
        }
        
        logger.info(
            "[ORATS_REQ] endpoint=%s requested_tickers=%d batch_size=%d sample_request=%s",
            endpoint_used, len(opra_symbols), len(batch), batch[:3],
        )
        
        t0 = time.perf_counter()
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                "[ORATS_RESP] status=ERROR latency_ms=%d error=%s",
                latency_ms, e
            )
            continue
        
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        if r.status_code != 200:
            logger.warning(
                "[ORATS_RESP] status=%d latency_ms=%d rows=0",
                r.status_code, latency_ms
            )
            continue
        
        try:
            raw = r.json()
        except ValueError:
            logger.warning("[ORATS_RESP] status=%d latency_ms=%d error=invalid_json", r.status_code, latency_ms)
            continue
        
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict) and "data" in raw:
            rows = raw.get("data", [])
        else:
            rows = []
        
        has_opra, non_null_bidask, non_null_oi, non_null_vol = _check_opra_fields_in_response(rows)
        
        logger.info(
            "[ORATS_RESP] endpoint=%s response_rows=%d non_null_bidask=%d non_null_oi=%d non_null_vol=%d latency_ms=%d sample_response_optionSymbols=%s",
            endpoint_used, len(rows), non_null_bidask, non_null_oi, non_null_vol, latency_ms,
            [(_normalize_occ_symbol(r.get("optionSymbol")) or _build_opra_symbol_from_row(r)) for r in rows[:3]],
        )
        
        total_rows += len(rows)
        total_with_bidask += non_null_bidask
        total_with_oi += non_null_oi
        total_with_vol += non_null_vol
        
        for row in rows:
            # Key by normalized OCC so merge matches BaseContract.opra_symbol (no space padding)
            opra_raw = row.get("optionSymbol") or ""
            opra = _normalize_occ_symbol(opra_raw) if opra_raw else None
            if not opra or len(opra) < 16:
                opra = _build_opra_symbol_from_row(row)
            if not opra:
                continue
            if len(sample_response_option_symbols) < 5:
                sample_response_option_symbols.append(opra)
            
            bid = row.get("bidPrice") or row.get("bid")
            ask = row.get("askPrice") or row.get("ask")
            oi = row.get("openInt") or row.get("openInterest") or row.get("open_interest") or row.get("oi")
            enrichment_map[opra] = {
                "bid": bid,
                "ask": ask,
                "volume": row.get("volume"),
                "open_interest": oi,
                "delta": row.get("delta"),
                "gamma": row.get("gamma"),
                "theta": row.get("theta"),
                "vega": row.get("vega"),
                "iv": row.get("iv") or row.get("smvVol"),
                "optionType": row.get("optionType"),
                "option_type": row.get("option_type"),
                "putCall": row.get("putCall"),
                "callPut": row.get("callPut"),
                "put_call": row.get("put_call"),
                "call_put": row.get("call_put"),
            }
    
    telemetry = {
        "endpoint_used": endpoint_used,
        "requested_tickers_count": len(opra_symbols),
        "response_rows": total_rows,
        "non_null_bidask": total_with_bidask,
        "non_null_oi": total_with_oi,
        "non_null_vol": total_with_vol,
        "sample_request_symbols": opra_symbols[:10],
        "sample_response_optionSymbols": sample_response_option_symbols[:5],
    }
    if total_with_bidask > 0:
        logger.info(
            "[ORATS_OPTIONS] SUMMARY enriched=%d/%d total_with_bidask=%d endpoint=%s",
            len(enrichment_map), len(opra_symbols), total_with_bidask, endpoint_used,
        )
    else:
        logger.info(
            "[ORATS_OPTIONS] SUMMARY enriched=%d/%d total_rows=%d contracts_with_bidask=0 endpoint=%s",
            len(enrichment_map), len(opra_symbols), total_rows, endpoint_used,
        )
    return enrichment_map, telemetry


def _empty_telemetry() -> Dict[str, Any]:
    """Return empty telemetry dict for no-op path."""
    return {
        "endpoint_used": None,
        "requested_tickers_count": 0,
        "response_rows": 0,
        "non_null_bidask": 0,
        "non_null_oi": 0,
        "non_null_vol": 0,
        "sample_request_symbols": [],
        "sample_response_optionSymbols": [],
    }


# ============================================================================
# STEP 4: Merge Chain and Liquidity
# ============================================================================

def _resolve_option_type_from_sources(
    enrichment: Dict[str, Any],
    base_option_type: str,
    opra: str,
) -> str:
    """
    Resolve option type from enrichment (all known keys), then base, then OCC symbol.
    Returns "PUT", "CALL", or "UNKNOWN" — never default to CALL when unknown.
    """
    OPTION_TYPE_KEYS = ("optionType", "option_type", "putCall", "callPut", "put_call", "call_put")
    for key in OPTION_TYPE_KEYS:
        raw = enrichment.get(key)
        if raw is None:
            continue
        s = str(raw).strip().upper()
        if s in ("P", "PUT", "PUTS"):
            return "PUT"
        if s in ("C", "CALL", "CALLS"):
            return "CALL"
    if base_option_type and str(base_option_type).upper() in ("PUT", "CALL"):
        return str(base_option_type).upper()
    if opra and len(opra) >= 13:
        c = opra[12].upper()  # OCC: ROOT(6)+YYMMDD(6)+C|P(1)
        if c == "P":
            return "PUT"
        if c == "C":
            return "CALL"
    return "UNKNOWN"


def merge_chain_and_liquidity(
    base_contracts: List[BaseContract],
    enrichment_map: Dict[str, Dict[str, Any]],
    underlying_price: Optional[float],
    fetched_at: str,
) -> List[EnrichedContract]:
    """
    Merge base chain with liquidity enrichment data.
    
    Args:
        base_contracts: List of BaseContract from /datav2/strikes
        enrichment_map: Dict of OPRA symbol -> liquidity data
        underlying_price: Underlying stock price
        fetched_at: ISO timestamp of fetch
    
    Returns:
        List of EnrichedContract with merged data
    """
    enriched_contracts = []
    
    for base in base_contracts:
        opra = base.opra_symbol
        enrichment = enrichment_map.get(opra, {})
        
        # Extract liquidity data (may be None if not enriched); map ORATS key variants
        bid = enrichment.get("bid") or enrichment.get("bidPrice")
        ask = enrichment.get("ask") or enrichment.get("askPrice")
        open_interest = enrichment.get("open_interest") or enrichment.get("openInterest") or enrichment.get("oi")
        
        # Compute mid if bid/ask available
        mid = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2
        
        resolved_type = _resolve_option_type_from_sources(
            enrichment, base.option_type, opra
        )
        contract = EnrichedContract(
            symbol=base.symbol,
            expiration=base.expiration,
            strike=base.strike,
            option_type=resolved_type,
            opra_symbol=opra,
            dte=base.dte,
            stock_price=underlying_price,
            bid=_safe_float(bid),
            ask=_safe_float(ask),
            mid=_safe_float(mid),
            volume=_safe_int(enrichment.get("volume")),
            open_interest=_safe_int(open_interest),
            delta=_safe_float(enrichment.get("delta")) or base.delta,
            gamma=_safe_float(enrichment.get("gamma")),
            theta=_safe_float(enrichment.get("theta")),
            vega=_safe_float(enrichment.get("vega")),
            iv=_safe_float(enrichment.get("iv")),
            enriched=bool(enrichment),
            fetched_at=fetched_at,
        )
        enriched_contracts.append(contract)
    
    return enriched_contracts


# ============================================================================
# Main Pipeline Function
# ============================================================================

def fetch_option_chain(
    symbol: str,
    dte_min: int = 21,
    dte_max: int = 45,
    enrich_all: bool = True,
    max_strikes_per_expiry: int = MAX_STRIKES_PER_EXPIRY,
    max_expiries: int = MAX_EXPIRIES,
    chain_mode: Optional[str] = None,
    delta_lo: Optional[float] = None,
    delta_hi: Optional[float] = None,
    strategy_mode: str = "CSP",
) -> OptionChainResult:
    """
    Fetch complete option chain with liquidity data using two-step pipeline.
    
    STEP 1: GET /datav2/strikes (or /datav2/live when chain_mode=LIVE) → base chain
    STEP 2: Build OPRA symbols
    STEP 3: GET /datav2/strikes/options (or live equivalent) → liquidity
    STEP 4: Merge results
    
    Args:
        symbol: Underlying ticker (e.g., AAPL)
        dte_min: Minimum days to expiration (default 21)
        dte_max: Maximum days to expiration (default 45)
        enrich_all: If True, enrich all contracts; if False, only enrich puts
        max_strikes_per_expiry: Max strikes to select per expiration
        max_expiries: Max expirations within DTE window
        chain_mode: Override: "DELAYED" | "LIVE" (from get_chain_source()). When None, use ORATS_DATA_MODE env.
    
    Returns:
        OptionChainResult with all contracts and stats
        
    Raises:
        OratsOpraModeError: If mode is live_derived (doesn't support OPRA fields)
    """
    start_time = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()
    if chain_mode is not None:
        mode = OratsDataMode.mode_from_chain_source(chain_mode)
    else:
        mode = OratsDataMode.get_current_mode()
    
    result = OptionChainResult(
        symbol=symbol.upper(),
        fetched_at=now_iso,
        data_mode=mode,
    )
    
    # FAIL FAST: Check mode supports OPRA fields
    if not OratsDataMode.supports_opra_fields(mode):
        error_msg = (
            f"OPRA fields unavailable in mode '{mode}'. "
            f"Set ORATS_DATA_MODE to 'delayed' or 'live' for liquidity data."
        )
        result.error = error_msg
        result.fetch_duration_ms = int((time.time() - start_time) * 1000)
        logger.error("[CHAIN_PIPELINE] %s: FAIL FAST - %s", symbol.upper(), error_msg)
        raise OratsOpraModeError(mode)
    
    # STEP 1: Fetch base chain (bounded)
    logger.info(
        "[CHAIN_PIPELINE] %s: STEP 1 - Fetching base chain (mode=%s, max_expiries=%d, max_strikes=%d)...",
        symbol.upper(), mode, max_expiries, max_strikes_per_expiry
    )
    base_contracts, underlying_price, error, base_strikes_rows_count = fetch_base_chain(
        symbol, dte_min, dte_max, max_strikes_per_expiry, max_expiries,
        chain_mode=chain_mode,
        delta_lo=delta_lo,
        delta_hi=delta_hi,
        strategy_mode=strategy_mode,
    )
    
    if error:
        result.error = error  # Canonical code: CSP_NO_OTM_STRIKES, REQUEST_SET_INVALID_CSP_STRIKE_RANGE, CC_NOT_IMPLEMENTED
        result.fetch_duration_ms = int((time.time() - start_time) * 1000)
        result.stage2_trace = {
            "error": error,
            "spot_used": underlying_price,
            "expirations_in_window": [],
            "requested_put_strikes": None,
            "sample_request_symbols": [],
            "message": "Base chain fetch failed",
        }
        logger.warning("[CHAIN_PIPELINE] %s: STEP 1 FAILED - %s", symbol.upper(), error)
        return result
    
    result.base_chain_count = len(base_contracts)
    result.underlying_price = underlying_price
    
    logger.info(
        "[CHAIN_PIPELINE] %s: STEP 1 COMPLETE - %d base contracts, underlying=$%.2f",
        symbol.upper(), len(base_contracts), underlying_price or 0
    )
    
    # STEP 2: Build OPRA symbols
    logger.info("[CHAIN_PIPELINE] %s: STEP 2 - Building OPRA symbols...", symbol.upper())
    opra_map = build_opra_symbols(base_contracts)
    result.opra_symbols_generated = len(opra_map)
    opra_symbols_to_enrich = list(opra_map.keys())

    # Phase 3.4: CSP fail-fast before /strikes/options — wrong type, ITM, or empty
    spot_check = underlying_price
    put_strikes_for_trace = [getattr(c, "strike", None) for c in base_contracts if getattr(c, "strike", None) is not None]
    requested_put_strikes_trace = (
        {"min": round(min(put_strikes_for_trace), 2), "max": round(max(put_strikes_for_trace), 2), "count": len(put_strikes_for_trace)}
        if put_strikes_for_trace else {"min": None, "max": None, "count": 0}
    )
    sample_request_symbols_trace = list(opra_map.keys())[:10]
    expirations_in_window_trace = sorted(
        set(e.isoformat()[:10] if hasattr(e, "isoformat") else str(e) for e in set(getattr(c, "expiration", None) for c in base_contracts) if e is not None)
    )
    _trace_base = {
        "spot_used": spot_check,
        "expirations_in_window": expirations_in_window_trace,
        "requested_put_strikes": requested_put_strikes_trace,
        "sample_request_symbols": sample_request_symbols_trace,
    }
    for opra, contract in opra_map.items():
        opt_type = getattr(contract, "option_type", "") or ""
        strike_val = getattr(contract, "strike", None) or 0
        if opt_type != "PUT":
            result.error = "CSP_REQUEST_BUILT_CALLS"
            result.fetch_duration_ms = int((time.time() - start_time) * 1000)
            result.stage2_trace = {"error": "CSP_REQUEST_BUILT_CALLS", **_trace_base, "message": "CALL in CSP request set"}
            logger.error("[CHAIN_PIPELINE] %s: CSP_REQUEST_BUILT_CALLS — option_type=%s", symbol.upper(), opt_type)
            return result
        if spot_check is not None and strike_val >= spot_check:
            result.error = "CSP_REQUEST_INCLUDED_ITM"
            result.fetch_duration_ms = int((time.time() - start_time) * 1000)
            result.stage2_trace = {"error": "CSP_REQUEST_INCLUDED_ITM", **_trace_base, "message": "PUT strike >= spot in CSP request set"}
            logger.error("[CHAIN_PIPELINE] %s: CSP_REQUEST_INCLUDED_ITM — strike %.2f >= spot %.2f", symbol.upper(), strike_val, spot_check)
            return result

    logger.info(
        "[CHAIN_PIPELINE] %s: STEP 2 COMPLETE - %d OPRA symbols to enrich",
        symbol.upper(), len(opra_symbols_to_enrich)
    )

    # STEP 3: Enrich with liquidity (non-derived endpoint only)
    logger.info("[CHAIN_PIPELINE] %s: STEP 3 - Enriching with liquidity...", symbol.upper())
    enrichment_map, strikes_telemetry = fetch_enriched_contracts(
        opra_symbols_to_enrich, require_opra_fields=True, chain_mode=chain_mode
    )
    result.enriched_count = len(enrichment_map)
    result.strikes_options_telemetry = strikes_telemetry
    
    logger.info(
        "[CHAIN_PIPELINE] %s: STEP 3 COMPLETE - %d contracts enriched",
        symbol.upper(), len(enrichment_map)
    )
    
    # STEP 4: Merge results
    logger.info("[CHAIN_PIPELINE] %s: STEP 4 - Merging chain and liquidity...", symbol.upper())
    result.contracts = merge_chain_and_liquidity(
        base_contracts, enrichment_map, underlying_price, now_iso
    )
    
    # Count contracts with valid liquidity
    result.contracts_with_liquidity = len([c for c in result.contracts if c.has_valid_liquidity])
    
    # DEBUG: One-line diagnostic for chain acquisition (confirms we have a real chain)
    puts_with_delta = [c for c in result.contracts if c.option_type == "PUT" and c.delta is not None and isinstance(c.delta, (int, float))]
    abs_deltas = [abs(float(d)) for d in (c.delta for c in puts_with_delta)]
    min_ad = min(abs_deltas) if abs_deltas else None
    max_ad = max(abs_deltas) if abs_deltas else None
    sample = sorted(abs_deltas)[:5] if abs_deltas else []
    logger.debug(
        "[CHAIN_ACQ] %s base_strikes_rows=%d occ_symbols=%d strikes_options_rows=%d merged=%d puts_with_delta=%d min_abs_put_delta=%s max_abs_put_delta=%s sample_abs_put_deltas=%s",
        symbol.upper(),
        base_strikes_rows_count,
        result.opra_symbols_generated,
        result.enriched_count,
        len(result.contracts),
        len(puts_with_delta),
        f"{min_ad:.3f}" if min_ad is not None else "n/a",
        f"{max_ad:.3f}" if max_ad is not None else "n/a",
        [round(x, 3) for x in sample],
    )

    # Stage-2 trace for validate_one_symbol / harness comparison (Phase 3.2: always populated)
    try:
        puts_list = result.puts
        put_strikes_requested = [getattr(c, "strike", None) for c in base_contracts if getattr(c, "strike", None) is not None]
        requested_put_strikes = (
            {"min": round(min(put_strikes_requested), 2), "max": round(max(put_strikes_requested), 2), "count": len(put_strikes_requested)}
            if put_strikes_requested else {"min": None, "max": None, "count": 0}
        )
        sample_request_symbols = list(opra_map.keys())[:10]
        # CSP required for eligibility: strike, expiration, delta, bid, ask (OI optional)
        REQUIRED_ATTRS_CSP = ("strike", "expiration", "delta", "bid", "ask")
        def _present(c: Any, name: str) -> bool:
            v = getattr(c, name, None)
            if name == "opra_symbol" and v is None:
                v = getattr(c, "option_symbol", None)
            return v is not None and (not isinstance(v, (int, float)) or True)
        puts_with_req = sum(1 for p in puts_list if all(_present(p, a) for a in REQUIRED_ATTRS_CSP))
        missing_counts_csp: Dict[str, int] = {}
        for fn in REQUIRED_ATTRS_CSP:
            missing_counts_csp[fn] = sum(1 for p in puts_list if not _present(p, fn))
        missing_bid = missing_counts_csp.get("bid", 0)
        missing_ask = missing_counts_csp.get("ask", 0)
        missing_delta = missing_counts_csp.get("delta", 0)
        missing_oi = sum(1 for p in puts_list if not _present(p, "open_interest"))
        sorted_abs_d = sorted(abs_deltas) if abs_deltas else []
        n = len(sorted_abs_d)
        def _pct(p: float) -> Optional[float]:
            if not n:
                return None
            idx = max(0, min(n - 1, int(n * p / 100.0)))
            return round(sorted_abs_d[idx], 4)
        base_url = OratsDataMode.get_base_url(mode)
        strikes_path = f"{base_url.rstrip('/')}{ORATS_STRIKES}"
        options_path = f"{base_url.rstrip('/')}{ORATS_STRIKES_OPTIONS}"
        tel = result.strikes_options_telemetry or {}
        spot = result.underlying_price
        # Phase 3.1: OTM counts and samples (CSP: strike < spot, CC: strike > spot)
        otm_puts = [p for p in puts_list if (getattr(p, "strike", None) or 0) < (spot or 0)]
        calls_list = result.calls
        otm_calls = [c for c in calls_list if (getattr(c, "strike", None) or 0) > (spot or 0)]
        DELTA_LO, DELTA_HI = 0.20, 0.40
        def _in_delta_band(c: Any) -> bool:
            d = getattr(c, "delta", None)
            if d is None:
                return False
            try:
                return DELTA_LO <= abs(float(d)) <= DELTA_HI
            except (TypeError, ValueError):
                return False
        otm_puts_in_delta_band = sum(1 for p in otm_puts if _in_delta_band(p))
        otm_calls_in_delta_band = sum(1 for c in otm_calls if _in_delta_band(c))
        calls_with_req = sum(1 for c in calls_list if all(_present(c, a) for a in REQUIRED_ATTRS_CSP))
        expirations_in_window = sorted(set(getattr(c, "expiration", None) for c in result.contracts if getattr(c, "expiration", None)))
        expirations_in_window = [e.isoformat()[:10] if hasattr(e, "isoformat") else str(e) for e in expirations_in_window]
        def _sample_row(c: Any) -> Dict[str, Any]:
            return {
                "strike": getattr(c, "strike", None),
                "abs_delta": round(abs(float(getattr(c, "delta", 0) or 0)), 4) if getattr(c, "delta", None) is not None else None,
                "bid": getattr(c, "bid", None),
                "ask": getattr(c, "ask", None),
                "open_interest": getattr(c, "open_interest", None),
            }
        sample_otm_puts = [_sample_row(p) for p in otm_puts[:10]]
        sample_otm_calls = [_sample_row(c) for c in otm_calls[:10]]
        otm_put_deltas = [abs(float(getattr(p, "delta", 0))) for p in otm_puts if getattr(p, "delta", None) is not None]
        otm_call_deltas = [abs(float(getattr(c, "delta", 0))) for c in otm_calls if getattr(c, "delta", None) is not None]
        def _delta_stats(deltas: List[float]) -> Dict[str, Any]:
            if not deltas:
                return {"min": None, "median": None, "max": None}
            s = sorted(deltas)
            n = len(s)
            return {
                "min": round(s[0], 4),
                "median": round(s[n // 2], 4),
                "max": round(s[-1], 4),
            }
        # Phase 3.4: request counts for truth telemetry (CSP = PUT-only, CC = CALL-only)
        puts_requested = len(base_contracts) if mode == "CSP" else 0
        calls_requested = 0 if mode == "CSP" else len(base_contracts)
        result.stage2_trace = {
            "spot": spot,
            "spot_used": spot,
            "dte_window": [dte_min, dte_max],
            "expirations_in_window": expirations_in_window,
            "requested_put_strikes": requested_put_strikes,
            "requested_tickers_count": len(base_contracts),
            "puts_requested": puts_requested,
            "calls_requested": calls_requested,
            "sample_request_symbols": sample_request_symbols,
            "response_rows": tel.get("response_rows"),
            "endpoints_used": [
                {"path": strikes_path, "mode": mode},
                {"path": tel.get("endpoint_used") or options_path, "mode": mode},
            ],
            "strikes_rows_count": base_strikes_rows_count,
            "strikes_options_rows_count": tel.get("response_rows") or result.enriched_count,
            "merged_count": len(result.contracts),
            "total_contracts_fetched": len(result.contracts),
            "puts_in_dte_count": len(puts_list),
            "otm_puts_in_dte": len(otm_puts),
            "otm_puts_in_delta_band": otm_puts_in_delta_band,
            "puts_with_required_fields": puts_with_req,
            "calls_in_dte_count": len(calls_list),
            "otm_calls_in_dte": len(otm_calls),
            "otm_calls_in_delta_band": otm_calls_in_delta_band,
            "calls_with_required_fields": calls_with_req,
            "puts_with_required_fields_count": puts_with_req,
            "missing_counts": {"bid": missing_bid, "ask": missing_ask, "open_interest": missing_oi, "delta": missing_delta},
            "missing_required_fields_counts": missing_counts_csp,
            "delta_abs_stats": {
                "min": round(min_ad, 4) if min_ad is not None else None,
                "p25": _pct(25),
                "median": _pct(50),
                "p75": _pct(75),
                "max": round(max_ad, 4) if max_ad is not None else None,
            },
            "delta_abs_otm_puts": _delta_stats(otm_put_deltas),
            "delta_abs_stats_otm_puts": _delta_stats(otm_put_deltas),
            "delta_abs_otm_calls": _delta_stats(otm_call_deltas),
            "sample_otm_puts": sample_otm_puts,
            "sample_otm_calls": sample_otm_calls,
            "sample_option_symbols": {
                "pre_merge": [getattr(c, "opra_symbol", None) or getattr(c, "option_symbol", None) for c in base_contracts[:10]],
                "post_merge": [getattr(c, "opra_symbol", None) or getattr(c, "option_symbol", None) for c in result.contracts[:10]],
                "post_dte": [getattr(c, "opra_symbol", None) or getattr(c, "option_symbol", None) for c in puts_list[:10]],
            },
            "rejection_counts": {},  # Filled by evaluator when building contract_data
        }
    except Exception as e:
        logger.warning("[CHAIN_PIPELINE] %s: stage2_trace build failed: %s", symbol.upper(), e)
        result.stage2_trace = {"error": str(e), "message": "Trace build failed"}

    # Merge trace fields into telemetry so diagnostics can show PUT-only request set
    if result.stage2_trace and isinstance(result.stage2_trace, dict):
        tel = result.strikes_options_telemetry or {}
        result.strikes_options_telemetry = {
            **tel,
            "requested_put_strikes": result.stage2_trace.get("requested_put_strikes"),
            "sample_request_symbols": result.stage2_trace.get("sample_request_symbols") or tel.get("sample_request_symbols") or [],
        }

    result.fetch_duration_ms = int((time.time() - start_time) * 1000)
    
    logger.info(
        "[CHAIN_PIPELINE] %s: PIPELINE COMPLETE - "
        "mode=%s base=%d opra=%d enriched=%d with_liquidity=%d duration_ms=%d",
        symbol.upper(),
        mode,
        result.base_chain_count,
        result.opra_symbols_generated,
        result.enriched_count,
        result.contracts_with_liquidity,
        result.fetch_duration_ms,
    )
    
    return result


# ============================================================================
# Liquidity Gate Check
# ============================================================================

def check_liquidity_gate(
    chain: OptionChainResult,
    min_valid_puts: int = 3,
    min_valid_contracts: int = 5,
) -> Tuple[bool, str]:
    """
    Check if option chain passes liquidity gate.
    
    Gate passes only when valid bid/ask/volume/OI exist on merged results.
    
    Args:
        chain: OptionChainResult from fetch_option_chain
        min_valid_puts: Minimum puts with valid liquidity (default 3)
        min_valid_contracts: Minimum total contracts with valid liquidity (default 5)
    
    Returns:
        Tuple of (passed: bool, reason: str)
    """
    if chain.error:
        return False, f"FAIL: {chain.error}"
    
    if not chain.contracts:
        return False, "FAIL: No contracts in chain"
    
    valid_puts = chain.valid_puts
    valid_total = chain.contracts_with_liquidity
    
    if len(valid_puts) < min_valid_puts:
        return False, f"FAIL: Only {len(valid_puts)} valid puts (need {min_valid_puts})"
    
    if valid_total < min_valid_contracts:
        return False, f"FAIL: Only {valid_total} contracts with liquidity (need {min_valid_contracts})"
    
    coverage_pct = chain.liquidity_coverage * 100
    return True, f"PASS: {len(valid_puts)} valid puts, {valid_total} total with liquidity ({coverage_pct:.1f}% coverage)"


__all__ = [
    # Data mode
    "OratsDataMode",
    # Errors
    "OratsChainError",
    "OratsOpraModeError",
    # Data models
    "BaseContract",
    "EnrichedContract",
    "OptionChainResult",
    # Pipeline functions
    "fetch_base_chain",
    "build_opra_symbols",
    "fetch_enriched_contracts",
    "merge_chain_and_liquidity",
    "fetch_option_chain",
    "check_liquidity_gate",
    # Capability probe
    "get_strikes_options_param_name",
]
