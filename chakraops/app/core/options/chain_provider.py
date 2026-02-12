# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Options Chain Provider interface and data models.

This module defines the abstract interface for fetching options chain data
and the data models for representing contracts, expirations, and chains.

Key design principles:
- Tri-state field values: VALID, MISSING, ERROR (never fake zeros)
- Provider-agnostic interface (ORATS, ThetaData, etc.)
- Comprehensive greeks and liquidity data
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from app.core.models.data_quality import (
    DataQuality,
    FieldValue,
    wrap_field_float,
    wrap_field_int,
    compute_data_completeness,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================

class OptionType(str, Enum):
    """Option type: PUT, CALL, or UNKNOWN (do not default unknown to CALL)."""
    PUT = "PUT"
    CALL = "CALL"
    UNKNOWN = "UNKNOWN"


class ContractLiquidityGrade(str, Enum):
    """Liquidity grade for a contract."""
    A = "A"  # Excellent: OI >= 1000, spread <= 5%
    B = "B"  # Good: OI >= 500, spread <= 10%
    C = "C"  # Fair: OI >= 100, spread <= 20%
    D = "D"  # Poor: below C thresholds
    F = "F"  # Fail: no data or invalid


# Liquidity thresholds
LIQUIDITY_THRESHOLDS = {
    "A": {"min_oi": 1000, "max_spread_pct": 0.05},
    "B": {"min_oi": 500, "max_spread_pct": 0.10},
    "C": {"min_oi": 100, "max_spread_pct": 0.20},
}


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class OptionContract:
    """
    Represents a single option contract with all relevant data.
    
    Fields use FieldValue wrapper to track data quality.
    """
    # Identifiers
    symbol: str
    expiration: date
    strike: float
    option_type: OptionType
    
    # Pricing (wrapped with data quality)
    bid: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "bid"))
    ask: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "ask"))
    mid: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "mid"))
    last: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "last"))
    
    # Liquidity
    open_interest: FieldValue[int] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "open_interest"))
    volume: FieldValue[int] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "volume"))
    
    # Greeks
    delta: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "delta"))
    gamma: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "gamma"))
    theta: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "theta"))
    vega: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "vega"))
    
    # Implied volatility
    iv: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "iv"))
    
    # Computed fields
    dte: int = 0  # Days to expiration
    spread: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not computed", "spread"))
    spread_pct: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not computed", "spread_pct"))
    
    # Metadata
    fetched_at: Optional[str] = None
    source: str = "UNKNOWN"
    
    def compute_derived_fields(self) -> None:
        """Compute derived fields like spread, spread_pct."""
        if self.bid.is_valid and self.ask.is_valid and self.bid.value is not None and self.ask.value is not None:
            spread_val = self.ask.value - self.bid.value
            self.spread = FieldValue(spread_val, DataQuality.VALID, "", "spread")
            
            # Compute mid if not set
            if not self.mid.is_valid:
                mid_val = (self.bid.value + self.ask.value) / 2
                self.mid = FieldValue(mid_val, DataQuality.VALID, "computed from bid/ask", "mid")
            
            # Compute spread percentage
            if self.mid.value and self.mid.value > 0:
                spread_pct_val = spread_val / self.mid.value
                self.spread_pct = FieldValue(spread_pct_val, DataQuality.VALID, "", "spread_pct")
    
    def get_liquidity_grade(self) -> ContractLiquidityGrade:
        """Compute liquidity grade based on OI and spread."""
        if not self.open_interest.is_valid or not self.spread_pct.is_valid:
            return ContractLiquidityGrade.F
        
        oi = self.open_interest.value or 0
        spread_pct = self.spread_pct.value or 1.0
        
        for grade in ["A", "B", "C"]:
            thresholds = LIQUIDITY_THRESHOLDS[grade]
            if oi >= thresholds["min_oi"] and spread_pct <= thresholds["max_spread_pct"]:
                return ContractLiquidityGrade(grade)
        
        return ContractLiquidityGrade.D
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return {
            "symbol": self.symbol,
            "expiration": self.expiration.isoformat(),
            "strike": self.strike,
            "option_type": self.option_type.value,
            "bid": self.bid.to_dict(),
            "ask": self.ask.to_dict(),
            "mid": self.mid.to_dict(),
            "last": self.last.to_dict(),
            "open_interest": self.open_interest.to_dict(),
            "volume": self.volume.to_dict(),
            "delta": self.delta.to_dict(),
            "gamma": self.gamma.to_dict(),
            "theta": self.theta.to_dict(),
            "vega": self.vega.to_dict(),
            "iv": self.iv.to_dict(),
            "dte": self.dte,
            "spread": self.spread.to_dict(),
            "spread_pct": self.spread_pct.to_dict(),
            "liquidity_grade": self.get_liquidity_grade().value,
            "fetched_at": self.fetched_at,
            "source": self.source,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """Convert to simplified dictionary with raw values."""
        return {
            "symbol": self.symbol,
            "expiration": self.expiration.isoformat(),
            "strike": self.strike,
            "option_type": self.option_type.value,
            "bid": self.bid.value,
            "ask": self.ask.value,
            "mid": self.mid.value,
            "open_interest": self.open_interest.value,
            "volume": self.volume.value,
            "delta": self.delta.value,
            "gamma": self.gamma.value,
            "theta": self.theta.value,
            "vega": self.vega.value,
            "iv": self.iv.value,
            "dte": self.dte,
            "spread": self.spread.value,
            "spread_pct": self.spread_pct.value,
            "liquidity_grade": self.get_liquidity_grade().value,
        }


@dataclass
class OptionsChain:
    """
    Represents an options chain for a symbol and expiration.
    """
    symbol: str
    expiration: date
    underlying_price: FieldValue[float] = field(default_factory=lambda: FieldValue(None, DataQuality.MISSING, "not fetched", "underlying_price"))
    
    # All contracts
    contracts: List[OptionContract] = field(default_factory=list)
    
    # Metadata
    fetched_at: Optional[str] = None
    source: str = "UNKNOWN"
    fetch_duration_ms: int = 0
    
    @property
    def puts(self) -> List[OptionContract]:
        """Get all put contracts."""
        return [c for c in self.contracts if c.option_type == OptionType.PUT]
    
    @property
    def calls(self) -> List[OptionContract]:
        """Get all call contracts."""
        return [c for c in self.contracts if c.option_type == OptionType.CALL]
    
    def get_contract(self, strike: float, option_type: OptionType) -> Optional[OptionContract]:
        """Get contract by strike and type."""
        for c in self.contracts:
            if c.strike == strike and c.option_type == option_type:
                return c
        return None
    
    def get_contracts_by_delta_range(
        self,
        option_type: OptionType,
        min_delta: float,
        max_delta: float,
        min_liquidity_grade: ContractLiquidityGrade = ContractLiquidityGrade.C,
    ) -> List[OptionContract]:
        """
        Get contracts within a delta range with minimum liquidity.
        For puts, delta is negative (-1 to 0).
        For calls, delta is positive (0 to 1).
        """
        results = []
        for c in self.contracts:
            if c.option_type != option_type:
                continue
            if not c.delta.is_valid or c.delta.value is None:
                continue
            
            delta = c.delta.value
            # Normalize for comparison (puts have negative delta)
            if option_type == OptionType.PUT:
                # For puts, we compare absolute values
                if not (min_delta <= delta <= max_delta):
                    continue
            else:
                # For calls
                if not (min_delta <= delta <= max_delta):
                    continue
            
            # Check liquidity
            grade = c.get_liquidity_grade()
            if grade.value > min_liquidity_grade.value:  # D > C > B > A
                continue
            
            results.append(c)
        
        return results
    
    def compute_data_completeness(self) -> tuple[float, List[str]]:
        """Compute overall data completeness for the chain."""
        if not self.contracts:
            return 0.0, ["no_contracts"]
        
        # Check key fields across contracts
        total_fields = 0
        valid_fields = 0
        missing_types = set()
        
        for c in self.contracts:
            for field_name in ["bid", "ask", "delta", "open_interest"]:
                total_fields += 1
                fv = getattr(c, field_name)
                if fv.is_valid:
                    valid_fields += 1
                else:
                    missing_types.add(field_name)
        
        completeness = valid_fields / total_fields if total_fields > 0 else 0.0
        return completeness, list(missing_types)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API serialization."""
        completeness, missing = self.compute_data_completeness()
        return {
            "symbol": self.symbol,
            "expiration": self.expiration.isoformat(),
            "underlying_price": self.underlying_price.to_dict(),
            "contract_count": len(self.contracts),
            "put_count": len(self.puts),
            "call_count": len(self.calls),
            "data_completeness": completeness,
            "missing_field_types": missing,
            "fetched_at": self.fetched_at,
            "source": self.source,
            "fetch_duration_ms": self.fetch_duration_ms,
        }


@dataclass
class ExpirationInfo:
    """Information about an expiration date."""
    expiration: date
    dte: int  # Days to expiration
    is_weekly: bool = False
    is_monthly: bool = False
    contract_count: int = 0


@dataclass 
class ChainProviderResult:
    """Result from a chain provider operation."""
    success: bool
    chain: Optional[OptionsChain] = None
    error: Optional[str] = None
    data_quality: DataQuality = DataQuality.VALID
    missing_fields: List[str] = field(default_factory=list)


# ============================================================================
# Provider Interface
# ============================================================================

@runtime_checkable
class OptionsChainProvider(Protocol):
    """
    Protocol for options chain data providers.
    
    Implementations must:
    - Return DataQuality.MISSING for unavailable fields (not fake zeros)
    - Handle rate limiting internally
    - Support caching
    """
    
    @property
    def name(self) -> str:
        """Provider name for logging."""
        ...
    
    def get_expirations(self, symbol: str) -> List[ExpirationInfo]:
        """
        Get available expiration dates for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            List of ExpirationInfo sorted by date
        """
        ...
    
    def get_chain(self, symbol: str, expiration: date) -> ChainProviderResult:
        """
        Get options chain for a symbol and expiration.
        
        Args:
            symbol: Stock ticker symbol
            expiration: Expiration date
            
        Returns:
            ChainProviderResult with chain data or error
        """
        ...
    
    def get_chains_batch(
        self, 
        symbol: str, 
        expirations: List[date],
        max_concurrent: int = 3,
        delta_lo: Optional[float] = None,
        delta_hi: Optional[float] = None,
    ) -> Dict[date, ChainProviderResult]:
        """
        Get multiple chains for a symbol (batch operation).
        
        Args:
            symbol: Stock ticker symbol
            expirations: List of expiration dates
            max_concurrent: Maximum concurrent requests
            delta_lo: Optional min |delta| for ORATS delta filter (Stage-2 CSP: 0.10)
            delta_hi: Optional max |delta| for ORATS delta filter (Stage-2 CSP: 0.45)
            
        Returns:
            Dict mapping expiration -> ChainProviderResult
        """
        ...


# ============================================================================
# Contract Selection Logic
# ============================================================================

@dataclass
class ContractSelectionCriteria:
    """Criteria for selecting an options contract."""
    option_type: OptionType
    target_delta: float  # e.g., -0.25 for CSP
    delta_tolerance: float = 0.10  # +/- range
    min_dte: int = 21
    max_dte: int = 45
    min_liquidity_grade: ContractLiquidityGrade = ContractLiquidityGrade.B
    min_credit: Optional[float] = None  # Minimum premium


@dataclass
class SelectedContract:
    """Result of contract selection."""
    contract: OptionContract
    selection_reason: str
    meets_all_criteria: bool
    criteria_results: Dict[str, bool] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return {
            "contract": self.contract.to_simple_dict(),
            "selection_reason": self.selection_reason,
            "meets_all_criteria": self.meets_all_criteria,
            "criteria_results": self.criteria_results,
        }


def select_contract(
    chain: OptionsChain,
    criteria: ContractSelectionCriteria,
) -> Optional[SelectedContract]:
    """
    Select the best contract from a chain based on criteria.
    
    For CSP (Cash-Secured Put):
    - Target delta around -0.20 to -0.30
    - Prefer higher premium (bid)
    - Require minimum liquidity
    
    Returns:
        SelectedContract if found, None otherwise
    """
    # Get contracts in delta range
    min_delta = criteria.target_delta - criteria.delta_tolerance
    max_delta = criteria.target_delta + criteria.delta_tolerance
    
    candidates = chain.get_contracts_by_delta_range(
        option_type=criteria.option_type,
        min_delta=min_delta,
        max_delta=max_delta,
        min_liquidity_grade=criteria.min_liquidity_grade,
    )
    
    if not candidates:
        return None
    
    # Score and rank candidates
    best_contract = None
    best_score = -float("inf")
    best_criteria_results = {}
    
    for c in candidates:
        criteria_results = {}
        score = 0
        
        # Check DTE
        dte_ok = criteria.min_dte <= c.dte <= criteria.max_dte
        criteria_results["dte_in_range"] = dte_ok
        if dte_ok:
            score += 10
        
        # Check liquidity
        grade = c.get_liquidity_grade()
        liquidity_ok = grade.value <= criteria.min_liquidity_grade.value
        criteria_results["liquidity_ok"] = liquidity_ok
        if liquidity_ok:
            score += 20
            # Bonus for better liquidity
            if grade == ContractLiquidityGrade.A:
                score += 10
            elif grade == ContractLiquidityGrade.B:
                score += 5
        
        # Check minimum credit
        if criteria.min_credit is not None and c.bid.is_valid:
            credit_ok = (c.bid.value or 0) >= criteria.min_credit
            criteria_results["min_credit_ok"] = credit_ok
            if credit_ok:
                score += 15
        else:
            criteria_results["min_credit_ok"] = True
        
        # Prefer delta closer to target
        if c.delta.is_valid and c.delta.value is not None:
            delta_diff = abs(c.delta.value - criteria.target_delta)
            score += max(0, 10 - delta_diff * 50)  # Up to 10 points
        
        # Prefer higher premium
        if c.bid.is_valid and c.bid.value:
            score += min(c.bid.value * 5, 20)  # Up to 20 points
        
        if score > best_score:
            best_score = score
            best_contract = c
            best_criteria_results = criteria_results
    
    if best_contract is None:
        return None
    
    meets_all = all(best_criteria_results.values())
    reason_parts = []
    if best_contract.delta.is_valid:
        reason_parts.append(f"delta={best_contract.delta.value:.2f}")
    reason_parts.append(f"DTE={best_contract.dte}")
    reason_parts.append(f"grade={best_contract.get_liquidity_grade().value}")
    if best_contract.bid.is_valid:
        reason_parts.append(f"bid=${best_contract.bid.value:.2f}")
    
    return SelectedContract(
        contract=best_contract,
        selection_reason=", ".join(reason_parts),
        meets_all_criteria=meets_all,
        criteria_results=best_criteria_results,
    )


__all__ = [
    "OptionType",
    "ContractLiquidityGrade",
    "OptionContract",
    "OptionsChain",
    "ExpirationInfo",
    "ChainProviderResult",
    "OptionsChainProvider",
    "ContractSelectionCriteria",
    "SelectedContract",
    "select_contract",
    "LIQUIDITY_THRESHOLDS",
]
