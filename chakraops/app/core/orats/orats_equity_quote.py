# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS Equity Quote Fetcher - Authoritative source for underlying bid/ask/volume.

This module fetches equity quote data for underlying tickers from ORATS.

CRITICAL: According to ORATS documentation:
- GET /datav2/strikes/options with tickers=<underlying> returns equity quote fields:
  stockPrice, bid, ask, bidSize, askSize, volume, quoteDate
- Multi-ticker requests are capped at 10 tickers per call
- This is the AUTHORITATIVE source for underlying bid/ask/volume

Endpoints used:
  - GET /datav2/strikes/options?token=...&tickers=AAPL,MSFT,...
    Returns underlying rows (no optionSymbol) with equity quote data

  - GET /datav2/ivrank?token=...&ticker=AAPL,MSFT,...
    Returns IV rank data (ivRank1m, ivPct1m)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from app.core.orats.endpoints import BASE_DATAV2, PATH_STRIKES_OPTIONS, PATH_IVRANK

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration (from single manifest)
# ============================================================================

ORATS_BASE_URL = BASE_DATAV2
ORATS_STRIKES_OPTIONS_PATH = PATH_STRIKES_OPTIONS
ORATS_IVRANK_PATH = PATH_IVRANK
TIMEOUT_SEC = 15
BATCH_SIZE = 10  # ORATS multi-ticker limit

# Rate limiting
RATE_LIMIT_CALLS_PER_SEC = 5.0


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

class OratsEquityQuoteError(Exception):
    """Raised when ORATS equity quote fetch fails."""
    
    def __init__(
        self,
        message: str,
        http_status: int = 0,
        endpoint: str = "",
        tickers: str = "",
    ) -> None:
        self.http_status = http_status
        self.endpoint = endpoint
        self.tickers = tickers
        super().__init__(message)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class EquityQuote:
    """Equity quote data from ORATS /strikes/options with underlying tickers."""
    symbol: str
    
    # Quote fields from ORATS
    price: Optional[float] = None  # stockPrice
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    quote_date: Optional[str] = None  # quoteDate
    
    # Metadata
    bid_size: Optional[int] = None  # bidSize
    ask_size: Optional[int] = None  # askSize
    
    # Data source tracking
    data_source: str = "strikes/options"
    fetched_at: Optional[str] = None
    
    # Fields that were present in response
    raw_fields_present: List[str] = field(default_factory=list)
    
    # Error info
    error: Optional[str] = None
    
    @property
    def has_bid_ask(self) -> bool:
        """Check if bid/ask are present."""
        return self.bid is not None and self.ask is not None
    
    @property
    def has_volume(self) -> bool:
        """Check if volume is present."""
        return self.volume is not None


@dataclass
class IVRankData:
    """IV rank data from ORATS /ivrank endpoint."""
    symbol: str
    
    # IV rank fields
    iv_rank: Optional[float] = None  # ivRank1m or ivPct1m
    iv_rank_1m: Optional[float] = None  # ivRank1m
    iv_pct_1m: Optional[float] = None  # ivPct1m
    
    # Metadata
    data_source: str = "ivrank"
    fetched_at: Optional[str] = None
    raw_fields_present: List[str] = field(default_factory=list)
    
    # Error info
    error: Optional[str] = None


@dataclass
class FullEquitySnapshot:
    """
    MarketSnapshot: combined equity quote + IV rank for the signal engine.
    Required: price (stockPrice), bid, ask, volume, quote_time (quoteDate), iv_rank.
    Only from delayed /strikes/options and /ivrank. No avg_volume (does not exist in ORATS).
    """
    symbol: str
    
    # From equity quote (required for completeness) — ONLY from delayed /strikes/options
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    quote_date: Optional[str] = None  # quoteDate -> quote_time in contract
    
    # From IV rank (required) — delayed /ivrank
    iv_rank: Optional[float] = None
    
    # Data source tracking per field
    data_sources: Dict[str, str] = field(default_factory=dict)
    raw_fields_present: List[str] = field(default_factory=list)
    
    # Missing REQUIRED fields only (used for completeness / BLOCKED)
    missing_fields: List[str] = field(default_factory=list)
    missing_reasons: Dict[str, str] = field(default_factory=dict)
    
    # Optional fields not available from ORATS (do not affect completeness)
    optional_not_available: Dict[str, str] = field(default_factory=dict)
    
    # Metadata
    fetched_at: Optional[str] = None
    errors: List[str] = field(default_factory=list)


# ============================================================================
# Run-level Cache
# ============================================================================

class EquityQuoteCache:
    """
    Run-level cache for equity quotes.
    
    Each evaluation run should create a new cache instance to avoid
    stale data across runs. The cache prevents duplicate API calls
    for the same tickers within a single run.
    """
    
    def __init__(self):
        self._equity_quotes: Dict[str, EquityQuote] = {}
        self._iv_ranks: Dict[str, IVRankData] = {}
        self._lock = threading.Lock()
        self._fetched_batches: Set[str] = set()  # Track which batches have been fetched
    
    def get_equity_quote(self, symbol: str) -> Optional[EquityQuote]:
        """Get cached equity quote if available."""
        with self._lock:
            return self._equity_quotes.get(symbol.upper())
    
    def set_equity_quote(self, symbol: str, quote: EquityQuote) -> None:
        """Cache equity quote."""
        with self._lock:
            self._equity_quotes[symbol.upper()] = quote
    
    def get_iv_rank(self, symbol: str) -> Optional[IVRankData]:
        """Get cached IV rank if available."""
        with self._lock:
            return self._iv_ranks.get(symbol.upper())
    
    def set_iv_rank(self, symbol: str, iv_rank: IVRankData) -> None:
        """Cache IV rank."""
        with self._lock:
            self._iv_ranks[symbol.upper()] = iv_rank
    
    def mark_batch_fetched(self, batch_key: str) -> bool:
        """
        Mark a batch as fetched. Returns True if batch was already fetched.
        """
        with self._lock:
            if batch_key in self._fetched_batches:
                return True
            self._fetched_batches.add(batch_key)
            return False


# Global cache for current run (reset at start of each evaluation)
_current_run_cache: Optional[EquityQuoteCache] = None


def get_run_cache() -> EquityQuoteCache:
    """Get or create cache for current evaluation run."""
    global _current_run_cache
    if _current_run_cache is None:
        _current_run_cache = EquityQuoteCache()
    return _current_run_cache


def reset_run_cache() -> None:
    """Reset cache at start of new evaluation run."""
    global _current_run_cache
    _current_run_cache = EquityQuoteCache()


# ============================================================================
# Helper Functions
# ============================================================================

def _get_orats_token() -> str:
    """Get ORATS API token from config."""
    from app.core.config.orats_secrets import ORATS_API_TOKEN
    return ORATS_API_TOKEN


def _extract_rows(raw: Any) -> List[Dict[str, Any]]:
    """Extract rows from ORATS response (handles list or {data: list} format)."""
    if isinstance(raw, list):
        return raw
    elif isinstance(raw, dict) and "data" in raw:
        data = raw.get("data")
        if isinstance(data, list):
            return data
    return []


def _batch_tickers(tickers: List[str], batch_size: int = BATCH_SIZE) -> List[List[str]]:
    """Split tickers into batches of batch_size."""
    return [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]


# ============================================================================
# Equity Quote Fetcher
# ============================================================================

def fetch_equity_quotes_batch(
    tickers: List[str],
    cache: Optional[EquityQuoteCache] = None,
) -> Dict[str, EquityQuote]:
    """
    Fetch equity quotes for multiple tickers using ORATS /strikes/options.
    
    CRITICAL: This endpoint accepts UNDERLYING tickers and returns equity fields:
    stockPrice, bid, ask, bidSize, askSize, volume, quoteDate.
    
    Automatically batches requests to respect ORATS 10-ticker limit.
    
    Args:
        tickers: List of underlying tickers (e.g., ["AAPL", "MSFT", "GOOGL"])
        cache: Optional cache instance (uses global if not provided)
    
    Returns:
        Dict mapping symbol -> EquityQuote
    """
    if not tickers:
        return {}
    
    cache = cache or get_run_cache()
    results: Dict[str, EquityQuote] = {}
    tickers_to_fetch: List[str] = []
    
    # Check cache first
    for ticker in tickers:
        ticker_upper = ticker.upper()
        cached = cache.get_equity_quote(ticker_upper)
        if cached:
            results[ticker_upper] = cached
            logger.debug("[EQUITY_QUOTE] %s: cache hit", ticker_upper)
        else:
            tickers_to_fetch.append(ticker_upper)
    
    if not tickers_to_fetch:
        logger.info("[ORATS_CACHE] equity_quotes: all %d tickers from cache (0 live calls)", len(tickers))
        return results
    
    logger.info(
        "[ORATS_CACHE] equity_quotes: %d live calls, %d cache hits, batch_size=%d",
        len(tickers_to_fetch), len(results), BATCH_SIZE
    )
    
    # Batch and fetch
    batches = _batch_tickers(tickers_to_fetch, BATCH_SIZE)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    for batch in batches:
        batch_key = ",".join(sorted(batch))
        if cache.mark_batch_fetched(batch_key):
            logger.debug("[ORATS_CACHE] equity_quotes batch already fetched: %s", batch[:3])
            continue
        
        try:
            params_for_cache = {"as_of": datetime.now(timezone.utc).date().isoformat()}
            try:
                from app.core.data.cache_policy import get_ttl
                from app.core.data.cache_store import fetch_batch_with_cache
                batch_results = fetch_batch_with_cache(
                    "quotes", batch, params_for_cache, get_ttl("quotes"),
                    lambda b=batch: _fetch_equity_quotes_single_batch(b),
                    serialize=lambda d: {k: asdict(v) for k, v in d.items()},
                    deserialize=lambda d: {k: EquityQuote(**v) for k, v in d.items()},
                )
            except ImportError:
                batch_results = _fetch_equity_quotes_single_batch(batch)
            for symbol, quote in batch_results.items():
                quote.fetched_at = now_iso
                results[symbol] = quote
                cache.set_equity_quote(symbol, quote)
        except OratsEquityQuoteError as e:
            logger.error("[EQUITY_QUOTE] Batch fetch failed: %s", e)
            # Create error entries for all tickers in batch
            for ticker in batch:
                results[ticker] = EquityQuote(
                    symbol=ticker,
                    error=str(e),
                    fetched_at=now_iso,
                )
                cache.set_equity_quote(ticker, results[ticker])
    
    return results


def _fetch_equity_quotes_single_batch(tickers: List[str]) -> Dict[str, EquityQuote]:
    """
    Fetch equity quotes for a single batch (max 10 tickers).
    
    Calls: GET /datav2/strikes/options?token=...&tickers=AAPL,MSFT,...
    
    The endpoint returns rows with equity quote data for underlying tickers.
    Rows WITHOUT optionSymbol are underlying rows.
    """
    _RATE_LIMITER.acquire()
    
    url = f"{ORATS_BASE_URL}{ORATS_STRIKES_OPTIONS_PATH}"
    tickers_param = ",".join(tickers)
    
    params = {
        "token": _get_orats_token(),
        "tickers": tickers_param,
    }
    
    logger.info(
        "[ORATS_EQ_REQ] GET %s tickers=%s (count=%d)",
        ORATS_STRIKES_OPTIONS_PATH, tickers[:3], len(tickers)
    )
    
    t0 = time.perf_counter()
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.error(
            "[ORATS_EQ_REQ] FAIL tickers=%s latency_ms=%d error=%s",
            tickers[:3], latency_ms, e
        )
        raise OratsEquityQuoteError(
            f"Request failed: {e}",
            endpoint=ORATS_STRIKES_OPTIONS_PATH,
            tickers=tickers_param[:100],
        )
    
    latency_ms = int((time.perf_counter() - t0) * 1000)
    
    if r.status_code != 200:
        logger.error(
            "[ORATS_EQ_REQ] HTTP %d tickers=%s latency_ms=%d response=%s",
            r.status_code, tickers[:3], latency_ms, r.text[:200]
        )
        raise OratsEquityQuoteError(
            f"HTTP {r.status_code}: {r.text[:200]}",
            http_status=r.status_code,
            endpoint=ORATS_STRIKES_OPTIONS_PATH,
            tickers=tickers_param[:100],
        )
    
    try:
        raw = r.json()
    except ValueError as e:
        logger.error("[ORATS_EQ_REQ] Invalid JSON for tickers=%s", tickers[:3])
        raise OratsEquityQuoteError(
            f"Invalid JSON: {e}",
            http_status=r.status_code,
            endpoint=ORATS_STRIKES_OPTIONS_PATH,
        )
    
    rows = _extract_rows(raw)
    
    # Mixed-row safety: if optionSymbol exists, treat as option row; do not merge into equity
    underlying_rows = [r for r in rows if not r.get("optionSymbol")]
    option_rows = [r for r in rows if r.get("optionSymbol")]
    
    logger.info(
        "[ORATS_EQ_RESP] latency_ms=%d total_rows=%d underlying_rows=%d option_rows=%d",
        latency_ms, len(rows), len(underlying_rows), len(option_rows)
    )
    
    # Log sample keys from first underlying row for debugging
    if underlying_rows:
        sample_keys = sorted(underlying_rows[0].keys())
        logger.debug("[ORATS_EQ_KEYS] Sample underlying row keys: %s", sample_keys[:20])
    
    # Parse underlying rows into EquityQuote objects
    results: Dict[str, EquityQuote] = {}
    
    for row in underlying_rows:
        ticker = row.get("ticker", "").upper()
        if not ticker:
            continue
        
        # Track which fields are present
        raw_fields = []
        
        # Extract equity fields
        price = None
        if "stockPrice" in row and row["stockPrice"] is not None:
            try:
                price = float(row["stockPrice"])
                raw_fields.append("stockPrice")
            except (TypeError, ValueError):
                pass
        
        bid = None
        if "bid" in row and row["bid"] is not None:
            try:
                bid = float(row["bid"])
                raw_fields.append("bid")
            except (TypeError, ValueError):
                pass
        
        ask = None
        if "ask" in row and row["ask"] is not None:
            try:
                ask = float(row["ask"])
                raw_fields.append("ask")
            except (TypeError, ValueError):
                pass
        
        volume = None
        if "volume" in row and row["volume"] is not None:
            try:
                volume = int(float(row["volume"]))
                raw_fields.append("volume")
            except (TypeError, ValueError):
                pass
        
        bid_size = None
        if "bidSize" in row and row["bidSize"] is not None:
            try:
                bid_size = int(float(row["bidSize"]))
                raw_fields.append("bidSize")
            except (TypeError, ValueError):
                pass
        
        ask_size = None
        if "askSize" in row and row["askSize"] is not None:
            try:
                ask_size = int(float(row["askSize"]))
                raw_fields.append("askSize")
            except (TypeError, ValueError):
                pass
        
        quote_date = row.get("quoteDate")
        if quote_date:
            raw_fields.append("quoteDate")
        
        quote = EquityQuote(
            symbol=ticker,
            price=price,
            bid=bid,
            ask=ask,
            volume=volume,
            bid_size=bid_size,
            ask_size=ask_size,
            quote_date=quote_date,
            data_source="strikes/options",
            raw_fields_present=raw_fields,
        )
        results[ticker] = quote
        
        # Debug log for sampled tickers
        if ticker in ("AAPL", "SPY", "MSFT"):
            logger.info(
                "[ORATS_EQ_SAMPLE] %s: price=%s bid=%s ask=%s volume=%s quote_date=%s fields=%s",
                ticker, price, bid, ask, volume, quote_date, raw_fields
            )
    
    # Runtime log: endpoint, symbols, http status, quote_date, field presence (single consolidated line per call)
    if results:
        first_sym = next(iter(results))
        q0 = results[first_sym]
        quote_date_log = q0.quote_date or ""
        field_presence = {
            "price": q0.price is not None,
            "volume": q0.volume is not None,
            "iv_rank": False,  # from ivrank endpoint only
            "bid": q0.bid is not None,
            "ask": q0.ask is not None,
            "open_interest": False,  # option-level in strikes/options
        }
        logger.info(
            "[ORATS_RESP] endpoint=%s symbol=%s http_status=%s quote_date=%s fields=%s",
            ORATS_STRIKES_OPTIONS_PATH, ",".join(tickers[:5]) + ("..." if len(tickers) > 5 else ""),
            200, quote_date_log, field_presence,
        )
    
    # Create empty entries for tickers that had no underlying row
    for ticker in tickers:
        ticker_upper = ticker.upper()
        if ticker_upper not in results:
            results[ticker_upper] = EquityQuote(
                symbol=ticker_upper,
                error="No underlying row returned by ORATS",
                data_source="strikes/options",
            )
            logger.warning("[ORATS_EQ_MISS] %s: no underlying row in response", ticker_upper)
    
    return results


def _parse_strikes_options_response(raw: Any) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Parse /strikes/options response and split underlying vs option rows.
    Returns (underlying_rows, underlying_count, option_count).
    Used by unit tests and merge report meta.
    """
    rows = _extract_rows(raw)
    underlying = [r for r in rows if not r.get("optionSymbol")]
    option = [r for r in rows if r.get("optionSymbol")]
    return underlying, len(underlying), len(option)


def build_merge_report(
    snapshots: Dict[str, FullEquitySnapshot],
    requested_tickers: List[str],
) -> Dict[str, Any]:
    """
    Build deterministic JSON report for equity + ivrank merge.
    Keys: requested_tickers, returned_quotes, returned_ivrank, excluded_by_reason.
    """
    requested = [t.upper() for t in requested_tickers]
    returned_quotes: List[str] = []
    returned_ivrank: List[str] = []
    excluded_by_reason: Dict[str, str] = {}
    for ticker in requested:
        snap = snapshots.get(ticker)
        if not snap:
            excluded_by_reason[ticker] = "missing_snapshot"
            continue
        has_quote = (
            snap.price is not None
            and snap.bid is not None
            and snap.ask is not None
            and snap.volume is not None
            and snap.quote_date is not None
        )
        if has_quote:
            returned_quotes.append(ticker)
        if snap.iv_rank is not None:
            returned_ivrank.append(ticker)
        reasons: List[str] = []
        if not has_quote:
            reasons.append("missing_equity_quote")
        if snap.iv_rank is None:
            reasons.append("missing_ivrank")
        if snap.missing_fields:
            reasons.append("missing_required:" + ",".join(sorted(snap.missing_fields)))
        if snap.errors:
            reasons.append("errors:" + ";".join(snap.errors[:2]))
        if reasons:
            excluded_by_reason[ticker] = ";".join(reasons)
    return {
        "requested_tickers": requested,
        "returned_quotes": sorted(returned_quotes),
        "returned_ivrank": sorted(returned_ivrank),
        "excluded_by_reason": dict(sorted(excluded_by_reason.items())),
    }


# ============================================================================
# IV Rank Fetcher
# ============================================================================

def fetch_iv_ranks_batch(
    tickers: List[str],
    cache: Optional[EquityQuoteCache] = None,
) -> Dict[str, IVRankData]:
    """
    Fetch IV rank data for multiple tickers using ORATS /ivrank.
    
    Calls: GET /datav2/ivrank?token=...&ticker=AAPL,MSFT,...
    
    Automatically batches requests to respect ORATS 10-ticker limit.
    
    Args:
        tickers: List of underlying tickers
        cache: Optional cache instance
    
    Returns:
        Dict mapping symbol -> IVRankData
    """
    if not tickers:
        return {}
    
    cache = cache or get_run_cache()
    results: Dict[str, IVRankData] = {}
    tickers_to_fetch: List[str] = []
    
    # Check cache first
    for ticker in tickers:
        ticker_upper = ticker.upper()
        cached = cache.get_iv_rank(ticker_upper)
        if cached:
            results[ticker_upper] = cached
        else:
            tickers_to_fetch.append(ticker_upper)
    
    if not tickers_to_fetch:
        logger.info("[ORATS_CACHE] ivrank: all %d tickers from cache (0 live calls)", len(tickers))
        return results
    
    logger.info("[ORATS_CACHE] ivrank: %d live calls, %d cache hits, batch_size=%d", len(tickers_to_fetch), len(results), BATCH_SIZE)
    
    # Batch and fetch
    batches = _batch_tickers(tickers_to_fetch, BATCH_SIZE)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    for batch in batches:
        try:
            params_for_cache = {"as_of": datetime.now(timezone.utc).date().isoformat()}
            try:
                from app.core.data.cache_policy import get_ttl
                from app.core.data.cache_store import fetch_batch_with_cache
                batch_results = fetch_batch_with_cache(
                    "iv_rank", batch, params_for_cache, get_ttl("iv_rank"),
                    lambda b=batch: _fetch_iv_ranks_single_batch(b),
                    serialize=lambda d: {k: asdict(v) for k, v in d.items()},
                    deserialize=lambda d: {k: IVRankData(**v) for k, v in d.items()},
                )
            except ImportError:
                batch_results = _fetch_iv_ranks_single_batch(batch)
            for symbol, iv_data in batch_results.items():
                iv_data.fetched_at = now_iso
                results[symbol] = iv_data
                cache.set_iv_rank(symbol, iv_data)
        except OratsEquityQuoteError as e:
            logger.error("[IVRANK] Batch fetch failed: %s", e)
            # Create error entries
            for ticker in batch:
                results[ticker] = IVRankData(
                    symbol=ticker,
                    error=str(e),
                    fetched_at=now_iso,
                )
                cache.set_iv_rank(ticker, results[ticker])
    
    return results


def _fetch_iv_ranks_single_batch(tickers: List[str]) -> Dict[str, IVRankData]:
    """
    Fetch IV rank for a single batch (max 10 tickers).
    
    Calls: GET /datav2/ivrank?token=...&ticker=AAPL,MSFT,...
    """
    _RATE_LIMITER.acquire()
    
    url = f"{ORATS_BASE_URL}{ORATS_IVRANK_PATH}"
    tickers_param = ",".join(tickers)
    
    params = {
        "token": _get_orats_token(),
        "ticker": tickers_param,  # Note: singular 'ticker' not 'tickers'
    }
    
    logger.info("[ORATS_IVRANK_REQ] GET %s ticker=%s", ORATS_IVRANK_PATH, tickers[:3])
    
    t0 = time.perf_counter()
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.error("[ORATS_IVRANK_REQ] FAIL ticker=%s latency_ms=%d error=%s", tickers[:3], latency_ms, e)
        raise OratsEquityQuoteError(
            f"Request failed: {e}",
            endpoint=ORATS_IVRANK_PATH,
            tickers=tickers_param[:100],
        )
    
    latency_ms = int((time.perf_counter() - t0) * 1000)
    
    if r.status_code != 200:
        logger.error(
            "[ORATS_IVRANK_REQ] HTTP %d ticker=%s latency_ms=%d response=%s",
            r.status_code, tickers[:3], latency_ms, r.text[:200]
        )
        raise OratsEquityQuoteError(
            f"HTTP {r.status_code}: {r.text[:200]}",
            http_status=r.status_code,
            endpoint=ORATS_IVRANK_PATH,
            tickers=tickers_param[:100],
        )
    
    try:
        raw = r.json()
    except ValueError as e:
        raise OratsEquityQuoteError(
            f"Invalid JSON: {e}",
            http_status=r.status_code,
            endpoint=ORATS_IVRANK_PATH,
        )
    
    rows = _extract_rows(raw)
    logger.info("[ORATS_IVRANK_RESP] latency_ms=%d rows=%d", latency_ms, len(rows))
    
    # Runtime log: endpoint, symbol, http status, quote_date (N/A for ivrank), field presence
    if rows:
        first_row = rows[0]
        field_presence = {
            "price": False,
            "volume": False,
            "iv_rank": (first_row.get("ivRank1m") is not None or first_row.get("ivPct1m") is not None),
            "bid": False,
            "ask": False,
            "open_interest": False,
        }
        logger.info(
            "[ORATS_RESP] endpoint=%s symbol=%s http_status=%s quote_date=n/a fields=%s",
            ORATS_IVRANK_PATH, ",".join(tickers[:5]) + ("..." if len(tickers) > 5 else ""),
            200, field_presence,
        )
        sample_keys = sorted(first_row.keys())
        logger.debug("[ORATS_IVRANK_KEYS] Sample row keys: %s", sample_keys)
    
    results: Dict[str, IVRankData] = {}
    
    for row in rows:
        ticker = row.get("ticker", "").upper()
        if not ticker:
            continue
        
        raw_fields = []
        
        # Extract IV rank - prefer ivRank1m, fall back to ivPct1m
        iv_rank_1m = None
        iv_pct_1m = None
        iv_rank = None
        
        if "ivRank1m" in row and row["ivRank1m"] is not None:
            try:
                iv_rank_1m = float(row["ivRank1m"])
                raw_fields.append("ivRank1m")
            except (TypeError, ValueError):
                pass
        
        if "ivPct1m" in row and row["ivPct1m"] is not None:
            try:
                iv_pct_1m = float(row["ivPct1m"])
                raw_fields.append("ivPct1m")
            except (TypeError, ValueError):
                pass
        
        # Use ivRank1m if available, else ivPct1m
        if iv_rank_1m is not None:
            iv_rank = iv_rank_1m
        elif iv_pct_1m is not None:
            # ivPct1m is already 0-100 scale
            iv_rank = iv_pct_1m
        
        iv_data = IVRankData(
            symbol=ticker,
            iv_rank=iv_rank,
            iv_rank_1m=iv_rank_1m,
            iv_pct_1m=iv_pct_1m,
            raw_fields_present=raw_fields,
        )
        results[ticker] = iv_data
        
        if ticker in ("AAPL", "SPY", "MSFT"):
            logger.info(
                "[ORATS_IVRANK_SAMPLE] %s: iv_rank=%s iv_rank_1m=%s iv_pct_1m=%s fields=%s",
                ticker, iv_rank, iv_rank_1m, iv_pct_1m, raw_fields
            )
    
    # Create empty entries for tickers with no data
    for ticker in tickers:
        ticker_upper = ticker.upper()
        if ticker_upper not in results:
            results[ticker_upper] = IVRankData(
                symbol=ticker_upper,
                error="No IV rank row returned by ORATS",
            )
            logger.warning("[ORATS_IVRANK_MISS] %s: no row in response", ticker_upper)
    
    return results


# ============================================================================
# Combined Snapshot Fetcher
# ============================================================================

def fetch_full_equity_snapshots(
    tickers: List[str],
    cache: Optional[EquityQuoteCache] = None,
) -> Dict[str, FullEquitySnapshot]:
    """
    Fetch complete equity snapshots (quote + IV rank) for multiple tickers.
    
    This is the main entry point for Stage 1 evaluation. Combines:
    - Equity quote from /strikes/options (price, bid, ask, volume, quote_date)
    - IV rank from /ivrank (iv_rank)
    
    Args:
        tickers: List of underlying tickers
        cache: Optional cache instance
    
    Returns:
        Dict mapping symbol -> FullEquitySnapshot
    """
    if not tickers:
        return {}
    
    cache = cache or get_run_cache()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Fetch both in parallel-ish (sequential batches, but both endpoints)
    logger.info("[EQUITY_SNAPSHOT] Fetching full snapshots for %d tickers", len(tickers))
    
    # Fetch equity quotes
    equity_quotes = fetch_equity_quotes_batch(tickers, cache)
    
    # Fetch IV ranks
    iv_ranks = fetch_iv_ranks_batch(tickers, cache)
    
    # Combine into full snapshots
    results: Dict[str, FullEquitySnapshot] = {}
    
    for ticker in tickers:
        ticker_upper = ticker.upper()
        
        eq = equity_quotes.get(ticker_upper)
        iv = iv_ranks.get(ticker_upper)
        
        snapshot = FullEquitySnapshot(
            symbol=ticker_upper,
            fetched_at=now_iso,
        )
        
        # Populate from equity quote
        if eq and not eq.error:
            snapshot.price = eq.price
            snapshot.bid = eq.bid
            snapshot.ask = eq.ask
            snapshot.volume = eq.volume
            snapshot.quote_date = eq.quote_date
            snapshot.raw_fields_present.extend(eq.raw_fields_present)
            
            # Track data sources
            if eq.price is not None:
                snapshot.data_sources["price"] = "strikes/options"
            if eq.bid is not None:
                snapshot.data_sources["bid"] = "strikes/options"
            if eq.ask is not None:
                snapshot.data_sources["ask"] = "strikes/options"
            if eq.volume is not None:
                snapshot.data_sources["volume"] = "strikes/options"
            if eq.quote_date:
                snapshot.data_sources["quote_date"] = "strikes/options"
        elif eq and eq.error:
            snapshot.errors.append(f"equity_quote: {eq.error}")
        
        # Populate from IV rank
        if iv and not iv.error:
            snapshot.iv_rank = iv.iv_rank
            snapshot.raw_fields_present.extend(iv.raw_fields_present)
            
            if iv.iv_rank is not None:
                snapshot.data_sources["iv_rank"] = "ivrank"
        elif iv and iv.error:
            snapshot.errors.append(f"iv_rank: {iv.error}")
        
        # Compute missing fields
        if snapshot.price is None:
            snapshot.missing_fields.append("price")
            snapshot.missing_reasons["price"] = eq.error if eq and eq.error else "Not in ORATS response"
        if snapshot.bid is None:
            snapshot.missing_fields.append("bid")
            snapshot.missing_reasons["bid"] = eq.error if eq and eq.error else "Not in ORATS response"
        if snapshot.ask is None:
            snapshot.missing_fields.append("ask")
            snapshot.missing_reasons["ask"] = eq.error if eq and eq.error else "Not in ORATS response"
        if snapshot.volume is None:
            snapshot.missing_fields.append("volume")
            snapshot.missing_reasons["volume"] = eq.error if eq and eq.error else "Not in ORATS response"
        if snapshot.iv_rank is None:
            snapshot.missing_fields.append("iv_rank")
            snapshot.missing_reasons["iv_rank"] = iv.error if iv and iv.error else "Not in ORATS response"
        
        results[ticker_upper] = snapshot
        
        logger.debug(
            "[EQUITY_SNAPSHOT] %s: price=%s bid=%s ask=%s volume=%s iv_rank=%s missing=%s",
            ticker_upper, snapshot.price, snapshot.bid, snapshot.ask,
            snapshot.volume, snapshot.iv_rank, snapshot.missing_fields
        )
    
    return results


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Exceptions
    "OratsEquityQuoteError",
    # Data classes
    "EquityQuote",
    "IVRankData",
    "FullEquitySnapshot",
    # Cache
    "EquityQuoteCache",
    "get_run_cache",
    "reset_run_cache",
    # Fetchers
    "fetch_equity_quotes_batch",
    "fetch_iv_ranks_batch",
    "fetch_full_equity_snapshots",
    # Merge report
    "build_merge_report",
    # Parser (for tests)
    "_parse_strikes_options_response",
]
