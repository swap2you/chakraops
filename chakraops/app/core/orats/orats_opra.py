# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS Delayed Data API - Strikes and Strikes-by-OPRA.

This module provides the canonical implementation for ORATS option chain
enrichment following the official ORATS Delayed Data API documentation:

BASE URL: https://api.orats.io/datav2

Endpoints:
  - GET /datav2/strikes
    Query param: `ticker` (comma-delimited up to 10)
    Optional filters: dte=30,45 and delta=.20,.35
    Returns strike grid with callBidPrice, callAskPrice, putBidPrice, putAskPrice, etc.

  - GET /datav2/strikes/options
    Query param: `tickers` (PLURAL - comma-delimited list of OCC option symbols ONLY).
    Returns option rows with optionSymbol, bidPrice, askPrice, volume, openInterest, greeks.
    UNDERLYING TICKERS ARE FORBIDDEN: calling with only an underlying (e.g. "AAPL") must raise.

OCC Option Symbol Format (per ORATS working examples - NO SPACE PADDING):
  optionSymbol = ROOT + YYMMDD + (P|C) + STRIKE*1000 (8 digits zero-padded)
  Example: AAPL + 2023-09-15 + C + 175.0 => AAPL230915C00175000
  Example: SPY + 2026-03-20 + P + 450.5 => SPY260320P00450500

CRITICAL: Do NOT use space-padded root (like "AAPL  "). ORATS examples use unpadded root.
"""

from __future__ import annotations

import logging
import re
import time
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

import requests

from app.core.orats.endpoints import BASE_DATAV2, PATH_STRIKES, PATH_STRIKES_OPTIONS

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration (from single manifest)
# ============================================================================

ORATS_DELAYED_BASE = BASE_DATAV2
ORATS_STRIKES_PATH = PATH_STRIKES
ORATS_STRIKES_OPTIONS_PATH = PATH_STRIKES_OPTIONS
TIMEOUT_SEC = 15

# Rate limiting
RATE_LIMIT_CALLS_PER_SEC = 5.0

# Bounded selection defaults
DEFAULT_MAX_EXPIRIES = 3
DEFAULT_MAX_STRIKES_PER_EXPIRY = 5


# ============================================================================
# Option Symbol Helpers
# ============================================================================

def to_yymmdd(date_str: str) -> str:
    """
    Convert date string to YYMMDD format.
    
    Args:
        date_str: Date in YYYY-MM-DD format (e.g., "2026-03-20")
    
    Returns:
        Date in YYMMDD format (e.g., "260320")
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%y%m%d")


def build_orats_option_symbol(
    root: str,
    expir_date: str,
    option_type: Literal["P", "C"],
    strike: float,
) -> str:
    """
    Build OCC/OSI option symbol in ORATS format.
    
    CRITICAL: ORATS examples use NO SPACE PADDING on root.
    Format: ROOT + YYMMDD + (P|C) + STRIKE*1000 (8 digits zero-padded)
    
    Args:
        root: Underlying ticker (e.g., "AAPL", "SPY")
        expir_date: Expiration in YYYY-MM-DD format (e.g., "2026-03-20")
        option_type: "P" for put, "C" for call
        strike: Strike price (e.g., 175.0, 450.50)
    
    Returns:
        Option symbol (e.g., "AAPL260320P00175000")
    
    Examples:
        >>> build_orats_option_symbol("AAPL", "2026-02-20", "P", 275.0)
        'AAPL260220P00275000'
        >>> build_orats_option_symbol("SPY", "2026-03-20", "C", 450.50)
        'SPY260320C00450500'
    """
    # Root: NO space padding per ORATS examples
    root_part = root.upper()
    
    # Expiration: YYMMDD
    exp_part = to_yymmdd(expir_date)
    
    # Option type: P or C
    type_part = option_type.upper()
    
    # Strike: multiply by 1000, round, pad to 8 digits
    strike_int = int(round(strike * 1000))
    strike_part = str(strike_int).zfill(8)
    
    return f"{root_part}{exp_part}{type_part}{strike_part}"


def validate_orats_option_symbol(sym: str) -> bool:
    """
    Validate ORATS option symbol format (no space padding in root).
    
    Expected format: ROOT + YYMMDD + (P|C) + 8 digits
    Minimum length: 1 (root) + 6 (date) + 1 (type) + 8 (strike) = 16
    
    Args:
        sym: Option symbol to validate
    
    Returns:
        True if valid format, False otherwise
    """
    if not sym or len(sym) < 16:
        return False
    
    # Pattern: letters + 6 digits + P/C + 8 digits
    pattern = r'^[A-Z]+\d{6}[PC]\d{8}$'
    return bool(re.match(pattern, sym))


def is_occ_option_symbol(s: str) -> bool:
    """
    Return True if s is a fully-formed OCC option symbol (suitable for /strikes/options).
    
    Accepts both unpadded root (AAPL260320P00175000) and space-padded root (AAPL  260320P00175000).
    Rejects underlying-only tickers (e.g. AAPL, SPY) which must NOT be passed to /strikes/options.
    
    Invariant: /datav2/strikes/options MUST ONLY be called with symbols that pass this check.
    """
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    if len(s) < 16:
        return False
    # ROOT (letters, optional spaces) + YYMMDD + P|C + 8 digits
    return bool(re.match(r'^[A-Z\s]+\d{6}[PC]\d{8}$', s))


def parse_orats_option_symbol(sym: str) -> Optional[Dict[str, Any]]:
    """
    Parse ORATS option symbol into components.
    
    Args:
        sym: Option symbol (e.g., "AAPL260320P00175000")
    
    Returns:
        Dict with root, expir_date, option_type, strike or None if invalid
    """
    if not validate_orats_option_symbol(sym):
        return None
    
    # Find where digits start (that's the YYMMDD)
    match = re.match(r'^([A-Z]+)(\d{6})([PC])(\d{8})$', sym)
    if not match:
        return None
    
    root, yymmdd, opt_type, strike8 = match.groups()
    
    # Parse date
    yy = int(yymmdd[:2])
    mm = int(yymmdd[2:4])
    dd = int(yymmdd[4:6])
    year = 2000 + yy
    expir_date = f"{year:04d}-{mm:02d}-{dd:02d}"
    
    # Parse strike
    strike = int(strike8) / 1000.0
    
    return {
        "root": root,
        "expir_date": expir_date,
        "option_type": "PUT" if opt_type == "P" else "CALL",
        "strike": strike,
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
# Exceptions
# ============================================================================

class OratsDelayedError(Exception):
    """Raised when ORATS Delayed Data API call fails."""
    
    def __init__(
        self,
        message: str,
        http_status: int = 0,
        endpoint: str = "",
        param_name: str = "",
        param_value: str = "",
    ) -> None:
        self.http_status = http_status
        self.endpoint = endpoint
        self.param_name = param_name
        self.param_value = param_value
        super().__init__(message)


# ============================================================================
# Helper Functions
# ============================================================================

def _get_orats_token() -> str:
    """Get ORATS API token from config."""
    from app.core.config.orats_secrets import ORATS_API_TOKEN
    return ORATS_API_TOKEN


def _redact_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Redact token from params for logging."""
    redacted = params.copy()
    if "token" in redacted:
        redacted["token"] = "***REDACTED***"
    return redacted


def _extract_rows(raw: Any) -> List[Dict[str, Any]]:
    """Extract rows from ORATS response (handles list or {data: list} format)."""
    if isinstance(raw, list):
        return raw
    elif isinstance(raw, dict) and "data" in raw:
        data = raw.get("data")
        if isinstance(data, list):
            return data
    return []


# ============================================================================
# ORATS Delayed Data Client
# ============================================================================

class OratsDelayedClient:
    """
    Client for ORATS Delayed Data API.
    
    Base URL: https://api.orats.io/datav2
    
    This class provides methods for:
    - get_strikes(): GET /datav2/strikes with `ticker` param
    - get_strikes_by_opra(): GET /datav2/strikes/options with `tickers` (PLURAL) param
    """
    
    def __init__(self, base_url: str = ORATS_DELAYED_BASE, timeout: int = TIMEOUT_SEC):
        self.base_url = base_url
        self.timeout = timeout
    
    def get_strikes(
        self,
        ticker: str,
        dte_min: Optional[int] = None,
        dte_max: Optional[int] = None,
        delta_min: Optional[float] = None,
        delta_max: Optional[float] = None,
        fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        GET /datav2/strikes - Fetch strikes grid for a ticker.
        
        Query param: `ticker` (singular, comma-delimited up to 10)
        
        Args:
            ticker: Underlying symbol (e.g., "AAPL")
            dte_min: Minimum days to expiration
            dte_max: Maximum days to expiration
            delta_min: Minimum delta filter
            delta_max: Maximum delta filter
            fields: Optional list of fields to request
        
        Returns:
            List of strike rows with callBidPrice, callAskPrice, putBidPrice, etc.
        """
        ticker_upper = ticker.upper()
        params_for_cache: Dict[str, Any] = {"as_of": date.today().isoformat()}
        if dte_min is not None:
            params_for_cache["dte_min"] = dte_min
        if dte_max is not None:
            params_for_cache["dte_max"] = dte_max
        if delta_min is not None:
            params_for_cache["delta_min"] = delta_min
        if delta_max is not None:
            params_for_cache["delta_max"] = delta_max
        if fields:
            params_for_cache["fields"] = ",".join(fields)

        def _do_fetch() -> List[Dict[str, Any]]:
            return self._get_strikes_http(
                ticker_upper, dte_min, dte_max, delta_min, delta_max, fields
            )

        try:
            from app.core.data.cache_policy import get_ttl
            from app.core.data.cache_store import fetch_with_cache
            return fetch_with_cache(
                "strikes", ticker_upper, params_for_cache, get_ttl("strikes"), _do_fetch
            )
        except ImportError:
            pass
        except OratsDelayedError:
            raise

        return self._get_strikes_http(
            ticker_upper, dte_min, dte_max, delta_min, delta_max, fields
        )

    def _get_strikes_http(
        self,
        ticker: str,
        dte_min: Optional[int],
        dte_max: Optional[int],
        delta_min: Optional[float],
        delta_max: Optional[float],
        fields: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """HTTP implementation of get_strikes (used by cache layer)."""
        _RATE_LIMITER.acquire()

        url = f"{self.base_url}{ORATS_STRIKES_PATH}"
        params: Dict[str, str] = {
            "token": _get_orats_token(),
            "ticker": ticker.upper(),
        }
        
        # Add optional filters
        if dte_min is not None and dte_max is not None:
            params["dte"] = f"{dte_min},{dte_max}"
        elif dte_min is not None:
            params["dte"] = str(dte_min)
        
        if delta_min is not None and delta_max is not None:
            params["delta"] = f"{delta_min},{delta_max}"
        
        if fields:
            params["fields"] = ",".join(fields)
        
        # Log request
        logger.info(
            "[ORATS_STRIKES] GET %s ticker=%s dte=%s delta=%s",
            ORATS_STRIKES_PATH,
            ticker.upper(),
            params.get("dte", "all"),
            params.get("delta", "all"),
        )
        
        t0 = time.perf_counter()
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                "[ORATS_STRIKES] FAIL ticker=%s latency_ms=%d error=%s",
                ticker.upper(), latency_ms, e
            )
            raise OratsDelayedError(
                f"Request failed: {e}",
                endpoint=ORATS_STRIKES_PATH,
                param_name="ticker",
                param_value=ticker.upper(),
            )
        
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        if r.status_code != 200:
            logger.error(
                "[ORATS_STRIKES] HTTP %d ticker=%s latency_ms=%d response=%s",
                r.status_code, ticker.upper(), latency_ms, r.text[:200]
            )
            raise OratsDelayedError(
                f"HTTP {r.status_code}: {r.text[:200]}",
                http_status=r.status_code,
                endpoint=ORATS_STRIKES_PATH,
                param_name="ticker",
                param_value=ticker.upper(),
            )
        
        try:
            raw = r.json()
        except ValueError as e:
            logger.error("[ORATS_STRIKES] Invalid JSON ticker=%s", ticker.upper())
            raise OratsDelayedError(
                f"Invalid JSON: {e}",
                http_status=r.status_code,
                endpoint=ORATS_STRIKES_PATH,
            )
        
        rows = _extract_rows(raw)
        
        # Log response summary
        sample_keys = list(rows[0].keys()) if rows else []
        logger.info(
            "[ORATS_STRIKES] OK ticker=%s latency_ms=%d rows=%d sample_keys=%s",
            ticker.upper(), latency_ms, len(rows), sample_keys[:10]
        )
        
        return rows
    
    def get_strikes_by_opra(
        self,
        tickers: List[str],
        batch_size: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        GET /datav2/strikes/options - Fetch option data by OCC option symbols ONLY.
        
        CRITICAL: Query param is `tickers` (PLURAL). Every element MUST be a
        fully-formed OCC option symbol. Underlying-only calls are FORBIDDEN
        and will raise OratsDelayedError.
        
        Args:
            tickers: List of OCC option symbols only (e.g. AAPL260320P00175000)
            batch_size: Max symbols per request (default 10)
        
        Returns:
            List of option rows: optionSymbol, bidPrice, askPrice, volume, openInterest, greeks
        
        Raises:
            OratsDelayedError: If any ticker is not a valid OCC option symbol
        """
        if not tickers:
            return []
        
        # INVARIANT: /strikes/options accepts OCC option symbols only. No underlyings.
        for t in tickers:
            if not is_occ_option_symbol(t):
                raise OratsDelayedError(
                    "strikes/options accepts OCC option symbols only; underlying ticker forbidden",
                    endpoint=ORATS_STRIKES_OPTIONS_PATH,
                    param_name="tickers",
                    param_value=t[:50] if t else "",
                )
        
        all_rows: List[Dict[str, Any]] = []
        
        # Process in batches
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            batch_rows = self._fetch_strikes_options_batch(batch)
            all_rows.extend(batch_rows)
        
        return all_rows
    
    def _fetch_strikes_options_batch(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """Fetch a single batch of strikes/options."""
        _RATE_LIMITER.acquire()
        
        url = f"{self.base_url}{ORATS_STRIKES_OPTIONS_PATH}"
        
        # CRITICAL: param name is `tickers` (PLURAL) for /strikes/options
        tickers_param = ",".join(tickers)
        params: Dict[str, str] = {
            "token": _get_orats_token(),
            "tickers": tickers_param,  # PLURAL - per ORATS docs
        }
        
        # Log request (sample first few tickers)
        sample_tickers = tickers[:3]
        logger.info(
            "[ORATS_STRIKES_OPTIONS] GET %s tickers=%s... (total=%d) param_name=tickers",
            ORATS_STRIKES_OPTIONS_PATH,
            sample_tickers,
            len(tickers),
        )
        
        t0 = time.perf_counter()
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                "[ORATS_STRIKES_OPTIONS] FAIL tickers=%s latency_ms=%d error=%s",
                sample_tickers, latency_ms, e
            )
            raise OratsDelayedError(
                f"Request failed: {e}",
                endpoint=ORATS_STRIKES_OPTIONS_PATH,
                param_name="tickers",
                param_value=tickers_param[:100],
            )
        
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        if r.status_code != 200:
            logger.error(
                "[ORATS_STRIKES_OPTIONS] HTTP %d tickers=%s latency_ms=%d response=%s",
                r.status_code, sample_tickers, latency_ms, r.text[:200]
            )
            raise OratsDelayedError(
                f"HTTP {r.status_code}: {r.text[:200]}",
                http_status=r.status_code,
                endpoint=ORATS_STRIKES_OPTIONS_PATH,
                param_name="tickers",
                param_value=tickers_param[:100],
            )
        
        try:
            raw = r.json()
        except ValueError as e:
            logger.error("[ORATS_STRIKES_OPTIONS] Invalid JSON")
            raise OratsDelayedError(
                f"Invalid JSON: {e}",
                http_status=r.status_code,
                endpoint=ORATS_STRIKES_OPTIONS_PATH,
            )
        
        rows = _extract_rows(raw)
        
        # Categorize rows for logging (underlying may have bid/ask or bidPrice/askPrice)
        option_rows = [r for r in rows if r.get("optionSymbol")]
        def _is_underlying_row(r: Dict[str, Any]) -> bool:
            if r.get("optionSymbol"):
                return False
            b = r.get("bid") or r.get("bidPrice")
            a = r.get("ask") or r.get("askPrice")
            return b is not None or a is not None
        underlying_rows = [r for r in rows if _is_underlying_row(r)]
        
        sample_keys = list(rows[0].keys()) if rows else []
        
        logger.info(
            "[ORATS_STRIKES_OPTIONS] OK latency_ms=%d total_rows=%d option_rows=%d underlying_rows=%d sample_keys=%s",
            latency_ms, len(rows), len(option_rows), len(underlying_rows), sample_keys[:10]
        )
        
        return rows


# ============================================================================
# Enrichment Data Classes
# ============================================================================

@dataclass
class OptionContract:
    """Option contract with OPRA enrichment data."""
    symbol: str  # Underlying
    option_symbol: str  # OCC option symbol
    expir_date: str  # YYYY-MM-DD
    strike: float
    option_type: str  # "PUT" or "CALL"
    dte: int
    
    # Liquidity fields
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    
    # Greeks
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    
    # Quote info
    quote_date: Optional[str] = None
    updated_at: Optional[str] = None
    
    @property
    def has_valid_liquidity(self) -> bool:
        """
        Check if contract has valid liquidity.
        
        Valid = bidPrice not null AND askPrice not null AND openInterest > 0
        (volume can be 0 or null, not fatal)
        """
        return (
            self.bid_price is not None and
            self.ask_price is not None and
            self.open_interest is not None and
            self.open_interest > 0
        )
    
    @property
    def mid_price(self) -> Optional[float]:
        """Calculate mid price if bid/ask available."""
        if self.bid_price is not None and self.ask_price is not None:
            return (self.bid_price + self.ask_price) / 2
        return None
    
    @property
    def spread(self) -> Optional[float]:
        """Calculate bid-ask spread."""
        if self.bid_price is not None and self.ask_price is not None:
            return self.ask_price - self.bid_price
        return None


@dataclass
class UnderlyingQuote:
    """Underlying stock quote from OPRA enrichment."""
    symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    stock_price: Optional[float] = None
    quote_date: Optional[str] = None
    
    @property
    def has_bid_ask(self) -> bool:
        """Check if bid/ask are present."""
        return self.bid is not None and self.ask is not None


@dataclass
class OpraEnrichmentResult:
    """Result of OPRA enrichment containing options and underlying data."""
    symbol: str
    underlying: Optional[UnderlyingQuote] = None
    options: List[OptionContract] = field(default_factory=list)
    
    # Stats
    strikes_rows: int = 0
    opra_symbols_built: int = 0
    option_rows_returned: int = 0
    underlying_row_returned: bool = False
    
    # Error
    error: Optional[str] = None
    
    @property
    def valid_puts(self) -> List[OptionContract]:
        """Get puts with valid liquidity."""
        return [o for o in self.options if o.option_type == "PUT" and o.has_valid_liquidity]
    
    @property
    def valid_calls(self) -> List[OptionContract]:
        """Get calls with valid liquidity."""
        return [o for o in self.options if o.option_type == "CALL" and o.has_valid_liquidity]
    
    @property
    def total_valid(self) -> int:
        """Total contracts with valid liquidity."""
        return len(self.valid_puts) + len(self.valid_calls)


# ============================================================================
# High-Level Enrichment Functions
# ============================================================================

def fetch_opra_enrichment(
    symbol: str,
    dte_min: int = 30,
    dte_max: int = 45,
    delta_min: Optional[float] = None,
    delta_max: Optional[float] = None,
    max_expiries: int = DEFAULT_MAX_EXPIRIES,
    max_strikes_per_expiry: int = DEFAULT_MAX_STRIKES_PER_EXPIRY,
    include_calls: bool = True,
) -> OpraEnrichmentResult:
    """
    Fetch OPRA-enriched option data for a symbol.
    
    Steps:
    1. Chain discovery: Call /datav2/strikes to get strike grid (underlying only).
    2. Contract selection + OCC construction: Build bounded OCC option symbols from chain.
    3. OPRA lookup: Call /datav2/strikes/options with OCC symbols ONLY (underlying forbidden).
    4. Liquidity validation: Parse option rows; valid liquidity = bid/ask present.
    
    Args:
        symbol: Underlying ticker (e.g., "AAPL")
        dte_min: Minimum DTE filter
        dte_max: Maximum DTE filter
        delta_min: Minimum delta filter (optional)
        delta_max: Maximum delta filter (optional)
        max_expiries: Max expirations to include
        max_strikes_per_expiry: Max strikes per expiration
        include_calls: Whether to include calls (default True)
    
    Returns:
        OpraEnrichmentResult with options and underlying quote
    """
    client = OratsDelayedClient()
    result = OpraEnrichmentResult(symbol=symbol.upper())
    
    # STEP 1: Get strikes grid
    try:
        strikes_rows = client.get_strikes(
            ticker=symbol,
            dte_min=dte_min,
            dte_max=dte_max,
            delta_min=delta_min,
            delta_max=delta_max,
        )
    except OratsDelayedError as e:
        result.error = f"Strikes fetch failed: {e}"
        logger.error("[OPRA_ENRICH] %s: strikes fetch failed: %s", symbol, e)
        return result
    
    result.strikes_rows = len(strikes_rows)
    
    if not strikes_rows:
        result.error = "No strikes data returned"
        logger.warning("[OPRA_ENRICH] %s: no strikes data", symbol)
        return result
    
    # STEP 2: Build bounded option symbol candidates
    option_symbols = _build_bounded_option_symbols(
        strikes_rows=strikes_rows,
        symbol=symbol,
        max_expiries=max_expiries,
        max_strikes_per_expiry=max_strikes_per_expiry,
        include_calls=include_calls,
    )
    
    result.opra_symbols_built = len(option_symbols)
    
    if not option_symbols:
        result.error = "No option symbols built from strikes"
        logger.warning("[OPRA_ENRICH] %s: no option symbols built", symbol)
        return result
    
    logger.info(
        "[OPRA_ENRICH] %s: built %d option symbols from %d strikes rows",
        symbol, len(option_symbols), len(strikes_rows)
    )
    
    # STEP 3: Call strikes/options with OCC option symbols ONLY. Underlying forbidden.
    tickers_to_fetch = option_symbols
    
    try:
        opra_rows = client.get_strikes_by_opra(tickers_to_fetch)
    except OratsDelayedError as e:
        result.error = f"Strikes/options fetch failed: {e}"
        logger.error("[OPRA_ENRICH] %s: strikes/options fetch failed: %s", symbol, e)
        return result
    
    # STEP 4: Parse rows into options and underlying
    option_rows = []
    underlying_row = None
    
    for row in opra_rows:
        if row.get("optionSymbol"):
            option_rows.append(row)
        elif row.get("ticker", "").upper() == symbol.upper():
            # This is the underlying row
            underlying_row = row
    
    result.option_rows_returned = len(option_rows)
    result.underlying_row_returned = underlying_row is not None
    
    logger.info(
        "[OPRA_ENRICH] %s: received %d option rows, underlying_row=%s",
        symbol, len(option_rows), result.underlying_row_returned
    )
    
    # Underlying quote: we do not request underlying from /strikes/options. Derive from strikes (stock price).
    if not underlying_row:
        stock_price = None
        for row in strikes_rows:
            sp = row.get("stockPrice") or row.get("stkPx")
            if sp is not None:
                stock_price = float(sp)
                break
        if stock_price is not None:
            result.underlying = UnderlyingQuote(
                symbol=symbol.upper(),
                bid=None,
                ask=None,
                volume=None,
                stock_price=stock_price,
                quote_date=None,
            )
    
    # Parse options
    for row in option_rows:
        opt_sym = row.get("optionSymbol", "")
        parsed = parse_orats_option_symbol(opt_sym)
        if not parsed:
            continue
        
        # ORATS may return openInterest or openInt
        open_interest = row.get("openInterest")
        if open_interest is None:
            open_interest = row.get("openInt")
        contract = OptionContract(
            symbol=symbol.upper(),
            option_symbol=opt_sym,
            expir_date=parsed["expir_date"],
            strike=parsed["strike"],
            option_type=parsed["option_type"],
            dte=row.get("dte", 0),
            bid_price=row.get("bidPrice"),
            ask_price=row.get("askPrice"),
            volume=row.get("volume"),
            open_interest=open_interest,
            delta=row.get("delta"),
            gamma=row.get("gamma"),
            theta=row.get("theta"),
            vega=row.get("vega"),
            iv=row.get("iv") or row.get("smvVol"),
            quote_date=row.get("quoteDate"),
            updated_at=row.get("updatedAt"),
        )
        result.options.append(contract)
    
    # Log summary
    logger.info(
        "[OPRA_ENRICH] %s: COMPLETE valid_puts=%d valid_calls=%d total_valid=%d underlying_bid_ask=%s",
        symbol,
        len(result.valid_puts),
        len(result.valid_calls),
        result.total_valid,
        result.underlying.has_bid_ask if result.underlying else False,
    )
    
    return result


def _build_bounded_option_symbols(
    strikes_rows: List[Dict[str, Any]],
    symbol: str,
    max_expiries: int,
    max_strikes_per_expiry: int,
    include_calls: bool,
) -> List[str]:
    """
    Build a bounded set of option symbols from strikes data.
    
    Selects up to max_expiries expirations and max_strikes_per_expiry strikes
    near ATM for each expiration.
    """
    if not strikes_rows:
        return []
    
    # Get stock price for ATM calculation
    stock_price = None
    for row in strikes_rows:
        sp = row.get("stockPrice") or row.get("stkPx")
        if sp:
            stock_price = float(sp)
            break
    
    # Group by expiration
    expiry_strikes: Dict[str, List[Dict]] = {}
    for row in strikes_rows:
        exp = row.get("expirDate")
        if not exp:
            continue
        if exp not in expiry_strikes:
            expiry_strikes[exp] = []
        expiry_strikes[exp].append(row)
    
    # Sort expirations by date and take max_expiries
    sorted_expiries = sorted(expiry_strikes.keys())[:max_expiries]
    
    option_symbols = []
    
    for exp in sorted_expiries:
        rows = expiry_strikes[exp]
        
        # Sort by proximity to ATM
        if stock_price:
            rows.sort(key=lambda r: abs(float(r.get("strike", 0)) - stock_price))
        
        # Take top N strikes
        selected = rows[:max_strikes_per_expiry]
        
        for row in selected:
            strike = row.get("strike")
            if strike is None:
                continue
            
            strike_f = float(strike)
            
            # Build PUT symbol
            put_sym = build_orats_option_symbol(symbol, exp, "P", strike_f)
            option_symbols.append(put_sym)
            
            # Build CALL symbol if requested
            if include_calls:
                call_sym = build_orats_option_symbol(symbol, exp, "C", strike_f)
                option_symbols.append(call_sym)
    
    return option_symbols


def check_opra_liquidity_gate(
    result: OpraEnrichmentResult,
    min_valid_puts: int = 3,
    min_valid_contracts: int = 5,
) -> Tuple[bool, str]:
    """
    Check if OPRA enrichment passes liquidity gate.
    
    Args:
        result: OpraEnrichmentResult from fetch_opra_enrichment
        min_valid_puts: Minimum valid puts required
        min_valid_contracts: Minimum total valid contracts required
    
    Returns:
        Tuple of (passed, reason)
    """
    if result.error:
        return False, f"FAIL: {result.error}"
    
    valid_puts = len(result.valid_puts)
    valid_calls = len(result.valid_calls)
    total_valid = result.total_valid
    
    if valid_puts < min_valid_puts:
        return False, f"FAIL: Only {valid_puts} valid puts (need {min_valid_puts})"
    
    if total_valid < min_valid_contracts:
        return False, f"FAIL: Only {total_valid} valid contracts (need {min_valid_contracts})"
    
    # Build example contract
    example = ""
    if result.valid_puts:
        p = result.valid_puts[0]
        example = f" [example: {p.option_symbol} bid={p.bid_price} ask={p.ask_price} OI={p.open_interest}]"
    
    return True, f"PASS: {valid_puts} valid puts, {valid_calls} valid calls, {total_valid} total{example}"


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Symbol helpers
    "to_yymmdd",
    "build_orats_option_symbol",
    "validate_orats_option_symbol",
    "is_occ_option_symbol",
    "parse_orats_option_symbol",
    # Client
    "OratsDelayedClient",
    "OratsDelayedError",
    # Data classes
    "OptionContract",
    "UnderlyingQuote",
    "OpraEnrichmentResult",
    # High-level functions
    "fetch_opra_enrichment",
    "check_opra_liquidity_gate",
]
