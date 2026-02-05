# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS Option Chain Loader - Canonical pipeline only.

Chain discovery and liquidity use the correct ORATS semantics:
  - Chain discovery: /datav2/strikes or /live/strikes (underlying ticker only).
  - OPRA lookup: /datav2/strikes/options ONLY with fully-formed OCC option symbols.
  Underlying-only calls to /strikes/options are forbidden.

This module delegates to app.core.options.orats_chain_pipeline (fetch_option_chain)
and maps the result to OptionChainLiquidity. No direct calls to /strikes/options
with underlying ticker.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# Normalized Liquidity Model
# ============================================================================

@dataclass(frozen=True)
class OptionContractLiquidity:
    """
    Normalized liquidity data for a single option contract.
    
    Frozen dataclass - immutable after creation.
    No filtering or strategy logic - pure data representation.
    """
    # Contract identifiers
    symbol: str
    expiration: date
    strike: float
    option_type: str  # "PUT" or "CALL"
    
    # Pricing
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    
    # Liquidity metrics
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    
    # Greeks
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    
    # Implied volatility
    iv: Optional[float] = None
    
    # DTE for convenience
    dte: int = 0
    
    # Metadata
    fetched_at: Optional[str] = None
    source: str = "ORATS"
    
    @property
    def has_valid_liquidity(self) -> bool:
        """Check if contract has minimum valid liquidity data."""
        return (
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
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "iv": self.iv,
            "dte": self.dte,
            "has_valid_liquidity": self.has_valid_liquidity,
            "spread": self.spread,
            "spread_pct": self.spread_pct,
            "fetched_at": self.fetched_at,
            "source": self.source,
        }


@dataclass
class OptionChainLiquidity:
    """
    Full option chain liquidity data for a symbol.
    Contains both puts and calls with liquidity metrics.
    """
    symbol: str
    underlying_price: Optional[float] = None
    contracts: List[OptionContractLiquidity] = field(default_factory=list)
    fetched_at: Optional[str] = None
    fetch_duration_ms: int = 0
    source: str = "ORATS"
    error: Optional[str] = None
    
    @property
    def puts(self) -> List[OptionContractLiquidity]:
        """Get all put contracts."""
        return [c for c in self.contracts if c.option_type == "PUT"]
    
    @property
    def calls(self) -> List[OptionContractLiquidity]:
        """Get all call contracts."""
        return [c for c in self.contracts if c.option_type == "CALL"]
    
    @property
    def contracts_with_liquidity(self) -> List[OptionContractLiquidity]:
        """Get contracts that have valid liquidity data."""
        return [c for c in self.contracts if c.has_valid_liquidity]
    
    @property
    def liquidity_coverage(self) -> float:
        """Percentage of contracts with valid liquidity."""
        if not self.contracts:
            return 0.0
        return len(self.contracts_with_liquidity) / len(self.contracts)
    
    def get_expirations(self) -> List[date]:
        """Get unique expiration dates sorted ascending."""
        exps = sorted(set(c.expiration for c in self.contracts))
        return exps
    
    def filter_by_expiration(self, expiration: date) -> List[OptionContractLiquidity]:
        """Get contracts for a specific expiration."""
        return [c for c in self.contracts if c.expiration == expiration]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "underlying_price": self.underlying_price,
            "contract_count": len(self.contracts),
            "contracts_with_liquidity": len(self.contracts_with_liquidity),
            "liquidity_coverage": self.liquidity_coverage,
            "expirations": [e.isoformat() for e in self.get_expirations()],
            "fetched_at": self.fetched_at,
            "fetch_duration_ms": self.fetch_duration_ms,
            "source": self.source,
            "error": self.error,
        }


# ============================================================================
# Exceptions (kept for API compatibility)
# ============================================================================

class OratsOptionChainError(Exception):
    """Raised when ORATS option chain fetch fails (e.g. pipeline error)."""
    
    def __init__(
        self,
        message: str,
        http_status: int = 0,
        response_snippet: str = "",
        symbol: str = "",
    ) -> None:
        self.http_status = http_status
        self.response_snippet = (response_snippet or "")[:500]
        self.symbol = symbol
        super().__init__(message)


# ============================================================================
# Main Loader Function - Delegates to canonical pipeline
# ============================================================================

def _enriched_to_liquidity(contract: Any, fetched_at: str) -> OptionContractLiquidity:
    """Map EnrichedContract from pipeline to OptionContractLiquidity."""
    return OptionContractLiquidity(
        symbol=contract.symbol,
        expiration=contract.expiration,
        strike=contract.strike,
        option_type=contract.option_type,
        bid=contract.bid,
        ask=contract.ask,
        mid=contract.mid,
        volume=contract.volume,
        open_interest=contract.open_interest,
        bid_size=None,
        ask_size=None,
        delta=contract.delta,
        gamma=contract.gamma,
        theta=contract.theta,
        vega=contract.vega,
        iv=contract.iv,
        dte=contract.dte,
        fetched_at=fetched_at,
        source="ORATS",
    )


def load_option_chain_liquidity(
    symbol: str,
    dte_min: int = 7,
    dte_max: int = 60,
) -> OptionChainLiquidity:
    """
    Load option chain with liquidity via the canonical ORATS pipeline.
    
    Pipeline: chain discovery (/datav2/strikes) → contract selection → OCC build
    → OPRA lookup (/datav2/strikes/options with OCC only) → liquidity validation.
    No underlying-only calls to /strikes/options.
    
    Args:
        symbol: Underlying ticker (e.g. AAPL)
        dte_min: Minimum days to expiration (default 7)
        dte_max: Maximum days to expiration (default 60)
    
    Returns:
        OptionChainLiquidity. error set on pipeline failure.
    """
    start_time = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    result = OptionChainLiquidity(
        symbol=symbol.upper(),
        fetched_at=now_iso,
        source="ORATS",
    )
    
    try:
        from app.core.options.orats_chain_pipeline import (
            fetch_option_chain,
            OratsOpraModeError,
            OratsChainError,
        )
        
        chain_result = fetch_option_chain(
            symbol=symbol,
            dte_min=dte_min,
            dte_max=dte_max,
            enrich_all=True,
        )
        
        if chain_result.error:
            result.error = chain_result.error
            result.fetch_duration_ms = int((time.time() - start_time) * 1000)
            logger.warning("[ORATS_CHAIN_LOADER] %s: pipeline error - %s", symbol.upper(), chain_result.error)
            return result
        
        result.underlying_price = chain_result.underlying_price
        result.contracts = [
            _enriched_to_liquidity(c, now_iso) for c in chain_result.contracts
        ]
        result.fetch_duration_ms = int((time.time() - start_time) * 1000)
        
        valid_count = len(result.contracts_with_liquidity)
        logger.info(
            "[ORATS_CHAIN_LOADER] %s: contracts=%d valid_liquidity=%d coverage=%.1f%% duration_ms=%d",
            symbol.upper(),
            len(result.contracts),
            valid_count,
            result.liquidity_coverage * 100,
            result.fetch_duration_ms,
        )
        
    except (OratsOpraModeError, OratsChainError) as e:
        result.error = str(e)
        result.fetch_duration_ms = int((time.time() - start_time) * 1000)
        logger.warning("[ORATS_CHAIN_LOADER] %s: pipeline failed - %s", symbol.upper(), e)
    except Exception as e:
        result.error = f"Unexpected error: {e}"
        result.fetch_duration_ms = int((time.time() - start_time) * 1000)
        logger.exception("[ORATS_CHAIN_LOADER] %s: unexpected error", symbol.upper())
    
    return result


def check_option_liquidity(
    symbol: str,
    dte_min: int = 21,
    dte_max: int = 45,
    min_contracts_with_liquidity: int = 5,
) -> Tuple[bool, str, Optional[OptionChainLiquidity]]:
    """
    Check if a symbol has sufficient option liquidity for trading.
    
    Args:
        symbol: Stock ticker symbol
        dte_min: Minimum DTE for target expiration window
        dte_max: Maximum DTE for target expiration window
        min_contracts_with_liquidity: Minimum contracts required with valid liquidity
    
    Returns:
        Tuple of (passed: bool, reason: str, chain: OptionChainLiquidity or None)
    """
    chain = load_option_chain_liquidity(symbol, dte_min, dte_max)
    
    if chain.error:
        return False, f"FAIL: {chain.error}", chain
    
    if not chain.contracts:
        return False, "FAIL: No option contracts found in DTE range", chain
    
    valid_count = len(chain.contracts_with_liquidity)
    
    if valid_count < min_contracts_with_liquidity:
        return (
            False,
            f"FAIL: Only {valid_count} contracts with valid liquidity (need {min_contracts_with_liquidity})",
            chain,
        )
    
    # Check for puts specifically (CSP strategy needs puts)
    valid_puts = [c for c in chain.contracts_with_liquidity if c.option_type == "PUT"]
    if len(valid_puts) < 3:
        return (
            False,
            f"FAIL: Only {len(valid_puts)} PUT contracts with valid liquidity",
            chain,
        )
    
    return (
        True,
        f"PASS: {valid_count} contracts with liquidity, {len(valid_puts)} valid puts",
        chain,
    )


__all__ = [
    "OptionContractLiquidity",
    "OptionChainLiquidity",
    "OratsOptionChainError",
    "load_option_chain_liquidity",
    "check_option_liquidity",
]
