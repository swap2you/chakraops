# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS Option Chain Pipeline - Two-Step Architecture.

This module implements the correct ORATS integration:

STEP 1: Discover option chain via /datav2/strikes
  - Input: underlying ticker (e.g., AAPL)
  - Output: list of (expirDate, strike, optionType) tuples

STEP 2: Enrich with liquidity via /datav2/strikes/options
  - Input: OPRA symbols (e.g., AAPL  260320C00175000)
  - Output: bid, ask, volume, openInterest, greeks

OPRA Symbol Format:
  - Root: 6 chars, left-aligned, space-padded (e.g., "AAPL  ")
  - Expiration: YYMMDD (e.g., "260320" for 2026-03-20)
  - Type: "C" or "P"
  - Strike: 8 digits, strike * 1000, zero-padded (e.g., "00175000" for $175)

Example: AAPL $175 Put expiring 2026-03-20 → "AAPL  260320P00175000"

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
        Build OPRA symbol for this contract.
        
        Format: ROOT(6) + YYMMDD + C/P + STRIKE*1000(8)
        Example: "AAPL  260320P00175000"
        """
        # Root: 6 chars, left-aligned, space-padded
        root = self.symbol.upper().ljust(6)
        
        # Expiration: YYMMDD
        exp_str = self.expiration.strftime("%y%m%d")
        
        # Type: C or P
        opt_type = "C" if self.option_type == "CALL" else "P"
        
        # Strike: multiply by 1000, pad to 8 digits
        strike_int = int(self.strike * 1000)
        strike_str = str(strike_int).zfill(8)
        
        return f"{root}{exp_str}{opt_type}{strike_str}"


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
        bid = row.get("bidPrice")
        ask = row.get("askPrice")
        oi = row.get("openInt") or row.get("openInterest")
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
    if delta_lo is not None and delta_hi is not None:
        params["delta"] = f"{delta_lo},{delta_hi}"
    
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
    
    # Sort expiries by date and take max_expiries
    sorted_expiries = sorted(expiry_strikes.keys())[:max_expiries]
    
    logger.info(
        "[ORATS_PARSE] total_expiries=%d selected_expiries=%d underlying=$%.2f",
        len(expiry_strikes), len(sorted_expiries), underlying_price or 0
    )
    
    # For each expiry, select bounded strikes near target moneyness
    for expiration in sorted_expiries:
        rows_for_expiry = expiry_strikes[expiration]
        
        # Sort strikes by proximity to target moneyness
        if underlying_price:
            target_put_strike = underlying_price * target_moneyness_put
            target_call_strike = underlying_price * target_moneyness_call
        else:
            # Fallback: use middle of strike range
            strikes = [float(r.get("strike", 0)) for r in rows_for_expiry]
            target_put_strike = target_call_strike = sum(strikes) / len(strikes) if strikes else 0
        
        # Sort by distance to put target and select top N
        rows_for_expiry_sorted = sorted(
            rows_for_expiry,
            key=lambda r: abs(float(r.get("strike", 0)) - target_put_strike)
        )
        selected_rows = rows_for_expiry_sorted[:max_strikes_per_expiry]
        
        for row in selected_rows:
            try:
                strike = float(row.get("strike"))
                dte = int(row.get("dte", 0))
                delta = row.get("delta")
                stock_price = row.get("stockPrice") or row.get("stkPx")
                
                # Create CALL contract
                call_contract = BaseContract(
                    symbol=symbol.upper(),
                    expiration=expiration,
                    strike=strike,
                    option_type="CALL",
                    dte=dte,
                    delta=float(delta) if delta is not None else None,
                    stock_price=float(stock_price) if stock_price else None,
                )
                all_contracts.append(call_contract)
                
                # Create PUT contract
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
    
    logger.info(
        "[ORATS_PARSE] valid_contracts=%d (bounded: %d expiries × %d strikes × 2 types)",
        len(all_contracts), len(sorted_expiries), max_strikes_per_expiry
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

def fetch_enriched_contracts(
    opra_symbols: List[str],
    batch_size: int = OPRA_BATCH_SIZE,
    require_opra_fields: bool = True,
    chain_mode: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    STEP 3 (OPRA lookup): Fetch liquidity data for OCC option symbols from /datav2/strikes/options.
    
    INVARIANT: /datav2/strikes/options MUST ONLY be called with fully-formed OCC option
    symbols. Underlying-only or mixed underlying+option calls are forbidden and will raise.
    
    Args:
        opra_symbols: List of OCC option symbols only (built from chain data)
        batch_size: Max symbols per request (default 10)
        require_opra_fields: If True, raise error if mode doesn't support OPRA fields
        chain_mode: Override: "DELAYED" | "LIVE". When None, use ORATS_DATA_MODE env.
    
    Returns:
        Dict mapping OPRA symbol -> enrichment data
        
    Raises:
        OratsChainError: If any symbol is not a valid OCC option symbol
        OratsOpraModeError: If mode is live_derived and require_opra_fields=True
    """
    if not opra_symbols:
        return {}
    
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
    
    # FAIL FAST: Check if mode supports OPRA fields
    if require_opra_fields and not OratsDataMode.supports_opra_fields(mode):
        logger.error(
            "[ORATS_OPTIONS] FAIL FAST: mode=%s does not support OPRA liquidity fields",
            mode
        )
        raise OratsOpraModeError(mode)
    
    base_url = OratsDataMode.get_base_url(mode)
    token = _get_orats_token()
    param_name = get_strikes_options_param_name()
    
    enrichment_map: Dict[str, Dict[str, Any]] = {}
    total_rows = 0
    total_with_bidask = 0
    total_with_oi = 0
    total_with_vol = 0
    
    # Process in batches
    for i in range(0, len(opra_symbols), batch_size):
        batch = opra_symbols[i:i + batch_size]
        
        _RATE_LIMITER.acquire()
        
        # Join OPRA symbols with commas
        tickers_param = ",".join(batch)
        
        url = f"{base_url}{ORATS_STRIKES_OPTIONS}"
        params = {
            "token": token,
            param_name: tickers_param,
        }
        
        # Log request
        logger.info(
            "[ORATS_REQ] base=%s path=%s mode=%s params=%s",
            base_url, ORATS_STRIKES_OPTIONS, mode, _redact_token(params)
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
                "[ORATS_RESP] status=%d latency_ms=%d rows=0 has_opra_fields=false",
                r.status_code, latency_ms
            )
            continue
        
        try:
            raw = r.json()
        except ValueError:
            logger.warning("[ORATS_RESP] status=%d latency_ms=%d error=invalid_json", r.status_code, latency_ms)
            continue
        
        # Extract rows
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict) and "data" in raw:
            rows = raw.get("data", [])
        else:
            rows = []
        
        # Check OPRA fields
        has_opra, non_null_bidask, non_null_oi, non_null_vol = _check_opra_fields_in_response(rows)
        
        # Log response
        logger.info(
            "[ORATS_RESP] status=%d latency_ms=%d rows=%d has_opra_fields=%s",
            r.status_code, latency_ms, len(rows), has_opra
        )
        
        # Log parse info
        if rows:
            row0_keys = list(rows[0].keys())
            logger.info(
                "[ORATS_PARSE] row0_keys=%s valid_contracts=%d "
                "non_null_bidask=%d non_null_oi=%d non_null_vol=%d",
                row0_keys, len(rows), non_null_bidask, non_null_oi, non_null_vol
            )
        
        total_rows += len(rows)
        total_with_bidask += non_null_bidask
        total_with_oi += non_null_oi
        total_with_vol += non_null_vol
        
        # Map rows back to OPRA symbols (optionSymbol is OCC, ticker is underlying)
        for row in rows:
            opra = row.get("optionSymbol") or row.get("ticker", "")
            
            # If opra matches one of our batch symbols, use it
            if opra in batch:
                pass  # opra already set
            else:
                # Try to reconstruct from row data (optionSymbol preferred; API returns ticker=underlying)
                root = (row.get("ticker") or "").split()[0] if row.get("ticker") else ""
                exp_str = row.get("expirDate", "")
                strike = row.get("strike")
                opt_type = (
                    row.get("optionType") or row.get("option_type") or
                    row.get("putCall") or row.get("callPut") or
                    row.get("put_call") or row.get("call_put") or ""
                )
                
                if root and exp_str and strike is not None:
                    try:
                        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                        opt_char = "C" if str(opt_type).strip().upper().startswith("C") else ("P" if str(opt_type).strip().upper().startswith("P") else None)
                        if opt_char is None:
                            continue
                        root_padded = root.upper().ljust(6)
                        exp_yymmdd = exp_date.strftime("%y%m%d")
                        strike_int = int(float(strike) * 1000)
                        strike_padded = str(strike_int).zfill(8)
                        opra = f"{root_padded}{exp_yymmdd}{opt_char}{strike_padded}"
                    except (ValueError, TypeError):
                        continue
                else:
                    continue
            
            enrichment_map[opra] = {
                "bid": row.get("bidPrice"),
                "ask": row.get("askPrice"),
                "volume": row.get("volume"),
                "open_interest": row.get("openInt") or row.get("openInterest"),
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
    
    # Log summary; "ORATS OK" in caller only when total_with_bidask > 0.
    if total_with_bidask > 0:
        logger.info(
            "[ORATS_OPTIONS] SUMMARY ORATS OK enriched=%d/%d total_with_bidask=%d",
            len(enrichment_map), len(opra_symbols), total_with_bidask,
        )
    else:
        logger.info(
            "[ORATS_OPTIONS] SUMMARY enriched=%d/%d total_rows=%d contracts_with_bidask=0",
            len(enrichment_map), len(opra_symbols), total_rows,
        )
    
    return enrichment_map


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
        
        # Extract liquidity data (may be None if not enriched)
        bid = enrichment.get("bid")
        ask = enrichment.get("ask")
        
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
            open_interest=_safe_int(enrichment.get("open_interest")),
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
    )
    
    if error:
        result.error = f"Base chain fetch failed: {error}"
        result.fetch_duration_ms = int((time.time() - start_time) * 1000)
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
    
    # Filter to only puts if not enriching all (for CSP strategy)
    if enrich_all:
        opra_symbols_to_enrich = list(opra_map.keys())
    else:
        opra_symbols_to_enrich = [
            opra for opra, contract in opra_map.items()
            if contract.option_type == "PUT"
        ]
    
    logger.info(
        "[CHAIN_PIPELINE] %s: STEP 2 COMPLETE - %d OPRA symbols to enrich",
        symbol.upper(), len(opra_symbols_to_enrich)
    )
    
    # STEP 3: Enrich with liquidity
    logger.info("[CHAIN_PIPELINE] %s: STEP 3 - Enriching with liquidity...", symbol.upper())
    enrichment_map = fetch_enriched_contracts(
        opra_symbols_to_enrich, require_opra_fields=True, chain_mode=chain_mode
    )
    result.enriched_count = len(enrichment_map)
    
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
