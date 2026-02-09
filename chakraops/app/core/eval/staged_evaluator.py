# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
2-Stage Universe Evaluator.

Stage 1: Stock quality + regime filters → candidates_stage1
  - Fetch stock summary data (price, IV, volume)
  - Apply basic quality gates
  - Determine regime context
  - Output: List of stage 1 candidates

Stage 2: For top K candidates, fetch chains and evaluate:
  - Fetch option expirations and chains
  - Apply liquidity gates (OI >= 500, spread <= 10%)
  - Select best contract based on delta/DTE criteria
  - Output: Full evaluation with selected contracts

Performance:
- Rate limiting via chain provider
- Caching at chain level
- Bounded concurrency (max 5 concurrent chain fetches)
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.core.models.data_quality import (
    DataQuality,
    FieldValue,
    wrap_field_float,
    wrap_field_int,
    compute_data_completeness_required,
    build_data_incomplete_reason,
)
from app.core.eval.strategy_rationale import StrategyRationale, build_rationale_from_staged
from app.core.eval.confidence_band import compute_confidence_band, CapitalHint
from app.core.eval.scoring import (
    compute_score_breakdown,
    build_rank_reasons,
)
from app.core.options.chain_provider import (
    OptionType,
    OptionContract,
    OptionsChain,
    ContractLiquidityGrade,
    ContractSelectionCriteria,
    SelectedContract,
    select_contract,
)
from app.core.options.orats_chain_provider import OratsChainProvider, get_chain_provider

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================

class EvaluationStage(str, Enum):
    """Stage reached in evaluation pipeline."""
    NOT_STARTED = "NOT_STARTED"
    STAGE1_ONLY = "STAGE1_ONLY"  # Stock quality evaluated only
    STAGE2_CHAIN = "STAGE2_CHAIN"  # Full chain evaluation completed


class StockVerdict(str, Enum):
    """Stage 1 verdict based on stock quality."""
    QUALIFIED = "QUALIFIED"  # Passes to stage 2
    HOLD = "HOLD"  # Does not qualify
    BLOCKED = "BLOCKED"  # Hard block
    ERROR = "ERROR"  # Error during evaluation


class FinalVerdict(str, Enum):
    """Final verdict after stage 2."""
    ELIGIBLE = "ELIGIBLE"  # Ready for trade
    HOLD = "HOLD"  # Not ready
    BLOCKED = "BLOCKED"  # Hard block
    UNKNOWN = "UNKNOWN"  # Error state


# Configuration
STAGE1_TOP_K = 20  # Top K candidates to advance to stage 2
STAGE2_MAX_CONCURRENT = 5  # Max concurrent chain fetches
TARGET_DTE_MIN = 21
TARGET_DTE_MAX = 45
TARGET_DELTA = -0.25  # For CSP
DELTA_TOLERANCE = 0.10
MIN_LIQUIDITY_GRADE = ContractLiquidityGrade.B
MIN_OPEN_INTEREST = 500
MAX_SPREAD_PCT = 0.10

# Scoring
SHORTLIST_SCORE_THRESHOLD = 70
DATA_INCOMPLETE_SCORE_CAP = 60


@dataclass
class StagedEvaluationResult:
    """
    Normalized return type for evaluate_universe_staged.
    Downstream must use .results and .exposure_summary; never assume a flat list.
    """
    results: List["FullEvaluationResult"]
    exposure_summary: Any  # ExposureSummary from position_awareness (avoid circular import)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Stage1Result:
    """Result of stage 1 evaluation for a symbol."""
    symbol: str
    source: str = "ORATS"
    
    # Stock data
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    avg_volume: Optional[int] = None
    iv_rank: Optional[float] = None
    quote_date: Optional[str] = None  # quoteDate from ORATS
    
    # Stage 1 verdict
    stock_verdict: StockVerdict = StockVerdict.ERROR
    stock_verdict_reason: str = ""
    stage1_score: int = 0  # 0-100
    
    # Context
    regime: Optional[str] = None
    risk_posture: Optional[str] = None
    
    # Data quality
    data_completeness: float = 0.0
    missing_fields: List[str] = field(default_factory=list)
    data_quality_details: Dict[str, str] = field(default_factory=dict)
    
    # Data source tracking (which ORATS endpoint provided each field)
    data_sources: Dict[str, str] = field(default_factory=dict)
    raw_fields_present: List[str] = field(default_factory=list)
    # Phase 8E: per-field source for diagnostics (ORATS | DERIVED | CACHED)
    field_sources: Dict[str, str] = field(default_factory=dict)
    
    # Metadata
    fetched_at: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Stage2Result:
    """Result of stage 2 evaluation for a symbol."""
    symbol: str
    
    # Chain data summary
    expirations_available: int = 0
    expirations_evaluated: int = 0
    contracts_evaluated: int = 0
    
    # Selected contract
    selected_contract: Optional[SelectedContract] = None
    selected_expiration: Optional[date] = None
    
    # Liquidity assessment
    liquidity_grade: Optional[str] = None
    liquidity_reason: str = ""
    liquidity_ok: bool = False
    
    # Chain data quality
    chain_completeness: float = 0.0
    chain_missing_fields: List[str] = field(default_factory=list)
    
    # Metadata
    chains_fetched_at: Optional[str] = None
    chain_fetch_duration_ms: int = 0
    error: Optional[str] = None
    # OPRA enhancement: count of valid contracts when liquidity_ok from strikes/options
    opra_valid_contracts: Optional[int] = None


@dataclass
class FullEvaluationResult:
    """Complete evaluation result combining both stages."""
    symbol: str
    source: str = "ORATS"
    
    # Stage tracking
    stage_reached: EvaluationStage = EvaluationStage.NOT_STARTED
    
    # Final verdict
    final_verdict: FinalVerdict = FinalVerdict.UNKNOWN
    primary_reason: str = ""
    confidence: float = 0.0
    score: int = 0  # 0-100
    
    # Stage 1 data
    stage1: Optional[Stage1Result] = None
    
    # Stage 2 data (if evaluated)
    stage2: Optional[Stage2Result] = None
    
    # Legacy compatibility fields
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    avg_volume: Optional[int] = None
    verdict: str = "UNKNOWN"
    liquidity_ok: bool = False
    liquidity_reason: str = ""
    options_available: bool = False
    options_reason: str = ""
    earnings_blocked: bool = False
    earnings_days: Optional[int] = None
    regime: Optional[str] = None
    risk: Optional[str] = None
    gates: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    candidate_trades: List[Dict[str, Any]] = field(default_factory=list)
    
    # Data quality
    data_completeness: float = 0.0
    missing_fields: List[str] = field(default_factory=list)
    data_quality_details: Dict[str, str] = field(default_factory=dict)
    
    # Data source tracking
    data_sources: Dict[str, str] = field(default_factory=dict)
    raw_fields_present: List[str] = field(default_factory=list)
    field_sources: Dict[str, str] = field(default_factory=dict)  # Phase 8E: ORATS | DERIVED | CACHED
    quote_date: Optional[str] = None  # quoteDate from ORATS
    iv_rank: Optional[float] = None  # Phase 6: from ivrank endpoint
    
    # Phase 8: Strategy explainability
    rationale: Optional[StrategyRationale] = None
    
    # Phase 9: Position-aware evaluation
    position_open: bool = False
    position_reason: Optional[str] = None  # e.g. POSITION_ALREADY_OPEN
    
    # Phase 10: Confidence band and capital hint
    capital_hint: Optional[CapitalHint] = None
    
    # Phase 3: Explainable scoring and capital-aware ranking
    score_breakdown: Optional[Dict[str, Any]] = None  # data_quality_score, regime_score, ...
    rank_reasons: Optional[Dict[str, Any]] = None  # { "reasons": [...], "penalty": "..." }
    csp_notional: Optional[float] = None  # selected_put_strike * 100
    notional_pct: Optional[float] = None  # csp_notional / account_equity
    band_reason: Optional[str] = None  # why this band (so Band C is not unexplained)
    
    # Verdict resolution metadata
    verdict_reason_code: Optional[str] = None
    data_incomplete_type: Optional[str] = None  # FATAL, INTRADAY, or None
    # OPRA authority: when set, stock bid/ask/volume were waived and liquidity is from /datav2/strikes/options
    waiver_reason: Optional[str] = None  # e.g. "DERIVED_FROM_OPRA"
    
    # Metadata
    fetched_at: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API serialization."""
        result = {
            "symbol": self.symbol,
            "source": self.source,
            "stage_reached": self.stage_reached.value,
            "final_verdict": self.final_verdict.value,
            "verdict": self.verdict,  # Legacy
            "primary_reason": self.primary_reason,
            "confidence": self.confidence,
            "score": self.score,
            "price": self.price,
            "bid": self.bid,
            "ask": self.ask,
            "volume": self.volume,
            "avg_volume": self.avg_volume,
            "regime": self.regime,
            "risk": self.risk,
            "liquidity_ok": self.liquidity_ok,
            "liquidity_reason": self.liquidity_reason,
            "options_available": self.options_available,
            "options_reason": self.options_reason,
            "data_completeness": self.data_completeness,
            "missing_fields": self.missing_fields,
            "data_quality_details": self.data_quality_details,
            "data_sources": self.data_sources,
            "raw_fields_present": self.raw_fields_present,
            "field_sources": getattr(self, "field_sources", {}),
            "quote_date": self.quote_date,
            "fetched_at": self.fetched_at,
            "error": self.error,
            "gates": self.gates,
            "blockers": self.blockers,
            "candidate_trades": self.candidate_trades,
            "rationale": self.rationale.to_dict() if self.rationale else None,
            "position_open": self.position_open,
            "position_reason": self.position_reason,
            "capital_hint": self.capital_hint.to_dict() if self.capital_hint else None,
            "waiver_reason": self.waiver_reason,
            "score_breakdown": self.score_breakdown,
            "rank_reasons": self.rank_reasons,
            "csp_notional": self.csp_notional,
            "notional_pct": self.notional_pct,
            "band_reason": self.band_reason,
        }
        
        # Add stage 2 specific fields
        if self.stage2 and self.stage2.selected_contract:
            result["selected_contract"] = self.stage2.selected_contract.to_dict()
            result["selected_expiration"] = self.stage2.selected_expiration.isoformat() if self.stage2.selected_expiration else None
        
        return result


# ============================================================================
# Stage 1: Stock Quality Evaluation
# ============================================================================

def evaluate_stage1(symbol: str) -> Stage1Result:
    """
    Stage 1: Evaluate stock quality and regime.
    
    Fetches equity quote data from ORATS endpoints:
    - /datav2/strikes/options with underlying ticker -> price, bid, ask, volume, quote_date
    - /datav2/ivrank -> iv_rank
    
    NOTE: avg_volume is NOT available from any ORATS endpoint.
    """
    from app.core.orats.orats_equity_quote import (
        fetch_full_equity_snapshots,
        OratsEquityQuoteError,
    )
    
    result = Stage1Result(symbol=symbol, source="ORATS")
    now_iso = datetime.now(timezone.utc).isoformat()
    result.fetched_at = now_iso
    
    # Track field quality
    field_quality: Dict[str, FieldValue] = {}
    
    try:
        # Fetch equity snapshot using the correct ORATS endpoints:
        # - /datav2/strikes/options with underlying ticker for bid/ask/volume
        # - /datav2/ivrank for iv_rank
        snapshots = fetch_full_equity_snapshots([symbol])
        
        if not snapshots or symbol.upper() not in snapshots:
            result.stock_verdict = StockVerdict.ERROR
            result.stock_verdict_reason = "No equity snapshot data returned"
            result.error = "No ORATS equity data"
            return result
        
        snapshot = snapshots[symbol.upper()]
        
        # ===========================================================================
        # DEBUG: Log ORATS response data for sampled tickers
        # ===========================================================================
        _SAMPLED_ORATS_KEYS: set = getattr(evaluate_stage1, "_sampled_orats_keys", set())
        if symbol.upper() in ("AAPL", "SPY") and symbol.upper() not in _SAMPLED_ORATS_KEYS:
            _SAMPLED_ORATS_KEYS.add(symbol.upper())
            evaluate_stage1._sampled_orats_keys = _SAMPLED_ORATS_KEYS  # type: ignore
            logger.info(
                "[ORATS_EQUITY_SAMPLE] %s: price=%s bid=%s ask=%s volume=%s iv_rank=%s "
                "quote_date=%s data_sources=%s raw_fields=%s missing=%s",
                symbol,
                snapshot.price, snapshot.bid, snapshot.ask, snapshot.volume,
                snapshot.iv_rank, snapshot.quote_date, snapshot.data_sources,
                snapshot.raw_fields_present, snapshot.missing_fields,
            )
        
        # ===========================================================================
        # ORATS Equity Data Mapping
        # ===========================================================================
        # Endpoints used:
        #   /datav2/strikes/options with underlying tickers:
        #     - stockPrice -> price
        #     - bid -> bid
        #     - ask -> ask
        #     - volume -> volume
        #     - quoteDate -> quote_date
        #
        #   /datav2/ivrank:
        #     - ivRank1m (or ivPct1m) -> iv_rank
        #
        # NOT AVAILABLE from any ORATS endpoint:
        #     - avg_volume (average volume) - requires external data source
        # ===========================================================================
        
        raw_price = snapshot.price
        raw_bid = snapshot.bid
        raw_ask = snapshot.ask
        raw_volume = snapshot.volume
        raw_avg_volume = snapshot.avg_volume  # Always None - not available from ORATS
        raw_iv_rank = snapshot.iv_rank
        
        # Log what we found
        if raw_price is None:
            logger.warning("[SNAPSHOT] %s: price missing - this is FATAL", symbol)
        logger.debug(
            "[SNAPSHOT] %s: price=%s bid=%s ask=%s volume=%s iv_rank=%s sources=%s",
            symbol, raw_price, raw_bid, raw_ask, raw_volume, raw_iv_rank, snapshot.data_sources
        )
        
        # MarketSnapshot required fields only (avg_volume excluded per ORATS reference)
        price_fv = wrap_field_float(raw_price, "price")
        bid_fv = wrap_field_float(raw_bid, "bid")
        ask_fv = wrap_field_float(raw_ask, "ask")
        volume_fv = wrap_field_int(raw_volume, "volume")
        # quote_time = quoteDate from ORATS; required for completeness
        quote_time_fv = FieldValue(
            value=snapshot.quote_date,
            quality=DataQuality.VALID if snapshot.quote_date else DataQuality.MISSING,
            reason="" if snapshot.quote_date else "quote_date not provided by source",
            field_name="quote_time",
        )
        iv_rank_fv = wrap_field_float(raw_iv_rank, "iv_rank")
        
        # Only REQUIRED fields for completeness (so 1.0 when all present)
        field_quality["price"] = price_fv
        field_quality["bid"] = bid_fv
        field_quality["ask"] = ask_fv
        field_quality["volume"] = volume_fv
        field_quality["quote_time"] = quote_time_fv
        field_quality["iv_rank"] = iv_rank_fv
        
        # Extract values
        result.price = price_fv.value if price_fv.is_valid else None
        result.bid = bid_fv.value if bid_fv.is_valid else None
        result.ask = ask_fv.value if ask_fv.is_valid else None
        result.volume = volume_fv.value if volume_fv.is_valid else None
        result.avg_volume = raw_avg_volume  # Always None from ORATS; optional, not in required
        result.iv_rank = iv_rank_fv.value if iv_rank_fv.is_valid else None
        result.quote_date = snapshot.quote_date
        
        # Store data source tracking from snapshot
        result.data_sources = snapshot.data_sources.copy()
        result.raw_fields_present = snapshot.raw_fields_present.copy()
        
        # Log snapshot fields: INFO for stage summary, DEBUG for populated values (UI/gates)
        logger.info(
            "[STAGE1] %s: snapshot fields - price=%s bid=%s ask=%s volume=%s iv_rank=%s quote_date=%s",
            symbol,
            f"${result.price:.2f}" if result.price else "MISSING",
            f"${result.bid:.2f}" if result.bid else "MISSING",
            f"${result.ask:.2f}" if result.ask else "MISSING",
            result.volume if result.volume else "MISSING",
            f"{result.iv_rank:.1f}" if result.iv_rank else "MISSING",
            result.quote_date or "MISSING",
        )
        # [SNAPSHOT] DEBUG: populated equity fields for downstream (UI, gates, scoring)
        logger.debug(
            "[SNAPSHOT] %s bid=%s ask=%s volume=%s avg_volume=%s iv_rank=%s sources=%s",
            symbol,
            result.bid,
            result.ask,
            f"{result.volume:,}" if result.volume is not None else None,
            f"{result.avg_volume:,}" if result.avg_volume is not None else None,
            result.iv_rank,
            result.data_sources,
        )
        
        # Phase 8E: Instrument-type-specific required fields (ETF/INDEX: bid, ask optional)
        from app.core.symbols.instrument_type import (
            classify_instrument,
            get_required_fields_for_instrument,
        )
        from app.core.symbols.derived_fields import derive_equity_fields
        
        inst = classify_instrument(symbol)
        required_by_inst = get_required_fields_for_instrument(inst)
        # Stage 1 field_quality uses "quote_time"; instrument_type uses "quote_date"
        required_keys = tuple(
            "quote_time" if k == "quote_date" else k for k in required_by_inst
        )
        
        # Phase 8E: Derivation — if bid/ask missing but derivable, treat as present
        derived = derive_equity_fields(
            price=raw_price, bid=raw_bid, ask=raw_ask, volume=raw_volume
        )
        for fname, eff_val in (("bid", derived.synthetic_bid), ("ask", derived.synthetic_ask)):
            if fname in field_quality and not field_quality[fname].is_valid and eff_val is not None:
                field_quality[fname] = FieldValue(
                    value=eff_val,
                    quality=DataQuality.VALID,
                    reason="derived (single quote or mid)",
                    field_name=fname,
                )
        
        # Per-field source for diagnostics (ORATS by default; DERIVED where we promoted)
        result.field_sources = {k: "ORATS" for k in field_quality}
        if derived.sources:
            for f in ("bid", "ask"):
                if field_quality.get(f) and field_quality[f].reason and "derived" in (field_quality[f].reason or "").lower():
                    result.field_sources[f] = "DERIVED"
        
        # Compute data completeness over instrument-specific REQUIRED fields only
        result.data_completeness, missing_required = compute_data_completeness_required(
            field_quality, required_keys
        )
        # Expose quote_time as quote_date in missing_fields for API consistency
        result.missing_fields = [
            "quote_date" if name == "quote_time" else name for name in missing_required
        ]
        for name, fv in field_quality.items():
            result.data_quality_details[name] = str(fv.quality)
        
        logger.info(
            "[STAGE1] %s: data_completeness=%.1f%% missing_fields=%s",
            symbol, result.data_completeness * 100, result.missing_fields
        )
        
        # Determine regime from IV
        if result.iv_rank is not None:
            if result.iv_rank < 30:
                result.regime = "BULL"
                result.risk_posture = "LOW"
            elif result.iv_rank > 70:
                result.regime = "BEAR"
                result.risk_posture = "HIGH"
            else:
                result.regime = "NEUTRAL"
                result.risk_posture = "MODERATE"
        else:
            result.regime = "UNKNOWN"
            result.risk_posture = "UNKNOWN"
        
        # Apply quality gates
        if not price_fv.is_valid or result.price is None:
            result.stock_verdict = StockVerdict.BLOCKED
            result.stock_verdict_reason = "DATA_INCOMPLETE_FATAL: No price data"
            return result
        
        # Check data completeness with market-status awareness
        # Import verdict resolver for proper classification
        try:
            from app.core.eval.verdict_resolver import (
                classify_data_incompleteness,
                MarketStatus,
                DataIncompleteType,
            )
            from app.api.server import get_market_phase
            
            market_phase = get_market_phase()
            market_status = MarketStatus.CLOSED if market_phase != "OPEN" else MarketStatus.OPEN
            
            data_type, data_reason = classify_data_incompleteness(
                result.missing_fields,
                market_status,
                has_options_chain=True,  # Will check in stage 2
            )
            
            # Only block if FATAL (missing price or critical fields)
            # With /strikes/options endpoint, bid/ask/volume should be available.
            # Only avg_volume is never available from ORATS.
            if data_type == DataIncompleteType.FATAL:
                result.stock_verdict = StockVerdict.HOLD
                result.stock_verdict_reason = data_reason
                return result
            elif data_type == DataIncompleteType.INTRADAY:
                # INTRADAY fields missing - could be market closed or ORATS didn't return them
                if market_status == MarketStatus.CLOSED:
                    result.stock_verdict_reason = f"Stock data OK ({data_reason})"
                else:
                    # Market OPEN - log which fields were missing
                    result.stock_verdict_reason = f"Stock data partial (missing: {', '.join(result.missing_fields)})"
                logger.debug(
                    "[STAGE1] %s: INTRADAY_ONLY fields missing but non-fatal: %s",
                    symbol, result.missing_fields
                )
            elif data_type == DataIncompleteType.NONE:
                # All fields present
                result.stock_verdict_reason = "Stock data complete"
            # NOTE: avg_volume is never available from ORATS and is always in missing_fields.
        except ImportError:
            # Fallback if verdict_resolver not available
            if result.data_completeness < 0.5 and result.price is None:
                result.stock_verdict = StockVerdict.HOLD
                result.stock_verdict_reason = build_data_incomplete_reason(result.missing_fields)
                return result
        
        # Compute stage 1 score
        result.stage1_score = _compute_stage1_score(result)
        
        # Qualified for stage 2
        result.stock_verdict = StockVerdict.QUALIFIED
        result.stock_verdict_reason = f"Stock qualified (score: {result.stage1_score})"
        
    except OratsEquityQuoteError as e:
        result.stock_verdict = StockVerdict.ERROR
        result.stock_verdict_reason = f"Equity data fetch error: {e}"
        result.error = str(e)
    except Exception as e:
        logger.exception("[STAGE1] Error evaluating %s: %s", symbol, e)
        result.stock_verdict = StockVerdict.ERROR
        result.stock_verdict_reason = f"Evaluation error: {e}"
        result.error = str(e)
    
    return result


def _compute_stage1_score(result: Stage1Result) -> int:
    """Compute stage 1 score based on stock quality."""
    score = 50  # Baseline
    
    # Regime bonus
    if result.regime == "BULL":
        score += 15
    elif result.regime == "NEUTRAL":
        score += 10
    elif result.regime == "BEAR":
        score -= 5
    
    # IV rank bonus (prefer higher IV for premium selling)
    if result.iv_rank is not None:
        if 30 <= result.iv_rank <= 70:
            score += 10  # Moderate IV is good
        elif result.iv_rank > 70:
            score += 5  # High IV has risk but good premium
    
    # Data completeness factor
    score = int(score * result.data_completeness)
    
    # Cap if incomplete
    if result.data_completeness < 0.75:
        score = min(score, DATA_INCOMPLETE_SCORE_CAP)
    
    return max(0, min(100, score))


# ============================================================================
# Stage 2: Chain Evaluation
# ============================================================================

def evaluate_stage2(
    symbol: str,
    stage1: Stage1Result,
    chain_provider: Optional[OratsChainProvider] = None,
) -> Stage2Result:
    """
    Stage 2: Fetch chains and evaluate contracts.
    
    Finds expirations in target DTE range and selects best contract.
    """
    result = Stage2Result(symbol=symbol)
    now_iso = datetime.now(timezone.utc).isoformat()
    result.chains_fetched_at = now_iso
    
    provider = chain_provider or get_chain_provider()
    start_time = time.time()
    
    try:
        # Get available expirations
        expirations = provider.get_expirations(symbol)
        result.expirations_available = len(expirations)
        
        if not expirations:
            result.error = "No expirations available"
            result.liquidity_reason = "No options chain data"
            return result
        
        # Filter to target DTE range
        target_expirations = [
            e for e in expirations
            if TARGET_DTE_MIN <= e.dte <= TARGET_DTE_MAX
        ]
        
        if not target_expirations:
            # Fall back to nearest expirations
            target_expirations = sorted(expirations, key=lambda e: e.dte)[:3]
        
        # Fetch chains for target expirations
        exp_dates = [e.expiration for e in target_expirations[:3]]  # Limit to 3
        chains = provider.get_chains_batch(symbol, exp_dates, max_concurrent=STAGE2_MAX_CONCURRENT)
        result.expirations_evaluated = len(chains)
        
        # Find best contract across all chains
        best_selection: Optional[SelectedContract] = None
        best_expiration: Optional[date] = None
        best_score = -float("inf")
        total_contracts = 0
        all_missing_fields = set()
        
        criteria = ContractSelectionCriteria(
            option_type=OptionType.PUT,  # CSP
            target_delta=TARGET_DELTA,
            delta_tolerance=DELTA_TOLERANCE,
            min_dte=TARGET_DTE_MIN,
            max_dte=TARGET_DTE_MAX,
            min_liquidity_grade=MIN_LIQUIDITY_GRADE,
        )
        
        for exp, chain_result in chains.items():
            if not chain_result.success or chain_result.chain is None:
                continue
            
            chain = chain_result.chain
            total_contracts += len(chain.contracts)
            
            # Track missing fields
            _, missing = chain.compute_data_completeness()
            all_missing_fields.update(missing)
            
            # Select best contract for this chain
            selection = select_contract(chain, criteria)
            if selection and selection.meets_all_criteria:
                # Score based on premium and liquidity
                contract = selection.contract
                selection_score = 0
                if contract.bid.is_valid and contract.bid.value:
                    selection_score += contract.bid.value * 10
                grade = contract.get_liquidity_grade()
                if grade == ContractLiquidityGrade.A:
                    selection_score += 20
                elif grade == ContractLiquidityGrade.B:
                    selection_score += 10
                
                if selection_score > best_score:
                    best_score = selection_score
                    best_selection = selection
                    best_expiration = exp
        
        result.contracts_evaluated = total_contracts
        result.chain_missing_fields = list(all_missing_fields)
        
        if best_selection:
            result.selected_contract = best_selection
            result.selected_expiration = best_expiration
            result.liquidity_grade = best_selection.contract.get_liquidity_grade().value
            result.liquidity_ok = True
            result.liquidity_reason = best_selection.selection_reason
            
            # Compute chain completeness
            result.chain_completeness = 1.0 - (len(all_missing_fields) / 4) if all_missing_fields else 1.0
        else:
            result.liquidity_ok = False
            result.liquidity_reason = "No contracts meeting criteria"
            if all_missing_fields:
                # Check if missing fields are intraday-only (OI, volume) and market is closed
                try:
                    from app.core.eval.verdict_resolver import (
                        classify_data_incompleteness,
                        MarketStatus,
                        DataIncompleteType,
                        INTRADAY_ONLY_FIELDS,
                    )
                    from app.api.server import get_market_phase
                    
                    market_phase = get_market_phase()
                    market_status = MarketStatus.CLOSED if market_phase != "OPEN" else MarketStatus.OPEN
                    
                    # Check if all missing fields are intraday-only
                    missing_lower = {f.lower() for f in all_missing_fields}
                    intraday_lower = {f.lower() for f in INTRADAY_ONLY_FIELDS} | {"oi", "openinterest", "open_interest"}
                    
                    if missing_lower.issubset(intraday_lower) and market_status == MarketStatus.CLOSED:
                        result.liquidity_reason = f"DATA_INCOMPLETE_INTRADAY: missing {', '.join(all_missing_fields)} (non-fatal, market CLOSED)"
                    else:
                        result.liquidity_reason = f"DATA_INCOMPLETE: missing {', '.join(all_missing_fields)}"
                except ImportError:
                    result.liquidity_reason = f"DATA_INCOMPLETE: missing {', '.join(all_missing_fields)}"
            result.chain_completeness = 0.5
        
    except Exception as e:
        logger.exception("[STAGE2] Error evaluating %s: %s", symbol, e)
        result.error = str(e)
        result.liquidity_reason = f"Chain fetch error: {e}"
    
    result.chain_fetch_duration_ms = int((time.time() - start_time) * 1000)
    return result


def _enhance_liquidity_with_pipeline(
    symbol: str,
    stage2: Stage2Result,
) -> Stage2Result:
    """
    Enhance stage 2 liquidity data using the ORATS option data pipeline.
    
    ORATS semantics (no underlying-only calls to /strikes/options):
      1. Chain discovery: /datav2/strikes (param: ticker) → base chain only.
      2. Contract selection + OCC construction: build OCC symbols from chain data.
      3. OPRA lookup: /datav2/strikes/options with OCC symbols ONLY (underlying forbidden).
      4. Liquidity validation: only contracts with bid/ask from OPRA count as valid.
    
    We do NOT assume OPRA returns chains; chain comes from /strikes. Liquidity
    validation occurs only after OPRA contract lookup. No silent fallbacks.
    
    Called when stage2.liquidity_ok is False from the standard live chain provider.
    
    Returns:
        Updated Stage2Result with enhanced liquidity data
    """
    try:
        from app.core.orats.orats_opra import (
            fetch_opra_enrichment,
            check_opra_liquidity_gate,
            OptionContract,
        )
    except ImportError:
        logger.warning("[STAGE2_ENHANCE] ORATS OPRA module not available for %s - cannot enhance", symbol)
        return stage2
    
    # Log why we're attempting enhancement
    logger.info(
        "[STAGE2_ENHANCE] %s: attempting OPRA enrichment, current_ok=%s reason='%s'",
        symbol, stage2.liquidity_ok, stage2.liquidity_reason
    )
    
    try:
        # Use the ORATS Delayed Data API with correct param names
        result = fetch_opra_enrichment(
            symbol=symbol,
            dte_min=TARGET_DTE_MIN,
            dte_max=TARGET_DTE_MAX,
            max_expiries=3,
            max_strikes_per_expiry=5,
            include_calls=True,  # Include both for flexibility
        )
        
        logger.info(
            "[STAGE2_ENHANCE] %s: OPRA returned strikes=%d opra_built=%d option_rows=%d valid_puts=%d valid_calls=%d underlying=%s error=%s",
            symbol,
            result.strikes_rows,
            result.opra_symbols_built,
            result.option_rows_returned,
            len(result.valid_puts),
            len(result.valid_calls),
            "yes" if result.underlying else "no",
            result.error or "none"
        )
        
        if result.error:
            logger.warning("[STAGE2_ENHANCE] %s: OPRA enrichment failed - %s", symbol, result.error)
            return stage2
        
        # OPRA is authority: >= 1 valid contract (bid>0, ask>0, OI>0) is enough - no secondary veto
        passed, gate_reason = check_opra_liquidity_gate(result, min_valid_puts=1, min_valid_contracts=1)
        
        logger.info(
            "[STAGE2_ENHANCE] %s: liquidity gate: %s - %s",
            symbol, "PASS" if passed else "FAIL", gate_reason
        )
        
        if not passed:
            logger.warning("[STAGE2_ENHANCE] %s: insufficient liquidity", symbol)
            stage2.liquidity_reason = f"DATA_INCOMPLETE: {gate_reason}"
            return stage2
        
        # Gate passed - find best put contract
        valid_puts = result.valid_puts
        
        # Find best put contract matching our criteria
        best_put: Optional[OptionContract] = None
        best_score = -float("inf")
        candidates_checked = 0
        
        for put in valid_puts:
            candidates_checked += 1
            
            # If no delta available, still consider the contract for EOD
            if put.delta is not None:
                delta_diff = abs(put.delta - TARGET_DELTA)
                # Be more lenient: allow wider delta range for EOD
                if delta_diff > DELTA_TOLERANCE * 1.5:  # 15% tolerance instead of 10%
                    continue
                delta_score = 10 - delta_diff * 50
            else:
                # No delta available - use OI-based scoring only
                delta_score = 0
            
            # Score based on liquidity
            score = delta_score
            if put.open_interest and put.open_interest >= MIN_OPEN_INTEREST:
                score += 20
            elif put.open_interest and put.open_interest >= 100:
                score += 10  # Partial credit for lower OI
            spread_pct = put.spread / put.mid_price if put.spread and put.mid_price else 1.0
            if spread_pct <= MAX_SPREAD_PCT:
                score += 15
            if put.bid_price:
                score += min(put.bid_price * 5, 20)  # Premium bonus
            
            if score > best_score:
                best_score = score
                best_put = put
        
        logger.info(
            "[STAGE2_ENHANCE] %s: checked %d candidates, best_score=%.1f",
            symbol, candidates_checked, best_score if best_put else 0
        )
        
        if best_put:
            # Build detailed reason string
            reason_parts = []
            if best_put.delta is not None:
                reason_parts.append(f"delta={best_put.delta:.2f}")
            reason_parts.append(f"DTE={best_put.dte}")
            if best_put.open_interest:
                reason_parts.append(f"OI={best_put.open_interest}")
            if best_put.bid_price:
                reason_parts.append(f"bid=${best_put.bid_price:.2f}")
            reason_parts.append("(enhanced)")
            
            # Update stage2 with enhanced data
            stage2.liquidity_ok = True
            stage2.liquidity_reason = ", ".join(reason_parts)
            stage2.liquidity_grade = _compute_liquidity_grade_from_opra(best_put)
            stage2.opra_valid_contracts = result.total_valid
            
            # Calculate coverage from result
            total_options = len(result.options)
            valid_total = result.total_valid
            stage2.chain_completeness = valid_total / total_options if total_options > 0 else 0.0
            stage2.chain_missing_fields = []  # Clear missing fields - we have liquidity!
            
            logger.info(
                "[STAGE2_ENHANCE] %s: SUCCESS - liquidity_ok=True, reason='%s'",
                symbol, stage2.liquidity_reason
            )
        else:
            logger.warning(
                "[STAGE2_ENHANCE] %s: no suitable put found despite %d valid puts",
                symbol, len(valid_puts)
            )
        
    except Exception as e:
        logger.exception("[STAGE2_ENHANCE] %s: OPRA enhancement failed with exception", symbol)
    
    return stage2


def _compute_liquidity_grade_from_opra(contract) -> str:
    """Compute liquidity grade for an OptionContract from OPRA enrichment."""
    oi = contract.open_interest or 0
    spread_pct = contract.spread / contract.mid_price if contract.spread and contract.mid_price else 1.0
    
    if oi >= 1000 and spread_pct <= 0.05:
        return "A"
    elif oi >= 500 and spread_pct <= 0.10:
        return "B"
    elif oi >= 100 and spread_pct <= 0.20:
        return "C"
    else:
        return "D"


# Keep old function names as aliases for compatibility
_enhance_liquidity_with_loader = _enhance_liquidity_with_pipeline
_compute_liquidity_grade_from_enriched = _compute_liquidity_grade_from_opra


# ============================================================================
# Full 2-Stage Evaluation
# ============================================================================

def evaluate_symbol_full(
    symbol: str,
    chain_provider: Optional[OratsChainProvider] = None,
    skip_stage2: bool = False,
) -> FullEvaluationResult:
    """
    Run full 2-stage evaluation for a symbol.
    
    Args:
        symbol: Stock ticker
        chain_provider: Optional provider instance
        skip_stage2: If True, only run stage 1
    
    Returns:
        FullEvaluationResult with complete evaluation data
    """
    result = FullEvaluationResult(symbol=symbol, source="ORATS")
    now_iso = datetime.now(timezone.utc).isoformat()
    result.fetched_at = now_iso
    
    # Stage 1
    stage1 = evaluate_stage1(symbol)
    result.stage1 = stage1
    result.stage_reached = EvaluationStage.STAGE1_ONLY
    
    # Copy stage 1 data to result
    result.price = stage1.price
    result.bid = stage1.bid
    result.ask = stage1.ask
    result.volume = stage1.volume
    result.avg_volume = stage1.avg_volume
    result.regime = stage1.regime
    result.risk = stage1.risk_posture
    result.data_completeness = stage1.data_completeness
    result.missing_fields = stage1.missing_fields.copy()
    result.data_quality_details = stage1.data_quality_details.copy()
    result.data_sources = stage1.data_sources.copy()
    result.raw_fields_present = stage1.raw_fields_present.copy()
    result.field_sources = getattr(stage1, "field_sources", {}).copy()
    result.quote_date = stage1.quote_date
    result.iv_rank = stage1.iv_rank
    
    # Add stage 1 gate
    result.gates.append({
        "name": "Stock Quality (Stage 1)",
        "status": "PASS" if stage1.stock_verdict == StockVerdict.QUALIFIED else "FAIL",
        "reason": stage1.stock_verdict_reason,
    })
    
    # Check if stage 1 passed
    if stage1.stock_verdict != StockVerdict.QUALIFIED:
        result.options_available = False
        result.options_reason = stage1.stock_verdict_reason
        
        if stage1.stock_verdict == StockVerdict.BLOCKED:
            result.final_verdict = FinalVerdict.BLOCKED
            result.verdict = "BLOCKED"
        elif stage1.stock_verdict == StockVerdict.ERROR:
            result.final_verdict = FinalVerdict.UNKNOWN
            result.verdict = "UNKNOWN"
            result.error = stage1.error
        else:
            result.final_verdict = FinalVerdict.HOLD
            result.verdict = "HOLD"
        
        result.primary_reason = stage1.stock_verdict_reason
        result.score = stage1.stage1_score
        return result
    
    # Skip stage 2 if requested
    if skip_stage2:
        result.options_available = True
        result.options_reason = "Stage 2 skipped"
        result.final_verdict = FinalVerdict.HOLD
        result.verdict = "HOLD"
        result.primary_reason = "Stock qualified, chain pending"
        result.score = stage1.stage1_score
        return result
    
    # Stage 2
    stage2 = evaluate_stage2(symbol, stage1, chain_provider)
    
    # Log stage 2 result before enhancement
    logger.info(
        "[STAGE2] %s: initial_liquidity_ok=%s reason='%s' missing_fields=%s",
        symbol, stage2.liquidity_ok, stage2.liquidity_reason, stage2.chain_missing_fields
    )
    
    # If liquidity check failed, try ORATS pipeline: chain discovery → OCC build → OPRA lookup
    # /strikes/options is called ONLY with OCC symbols; liquidity validated after OPRA response
    if not stage2.liquidity_ok:
        stage2 = _enhance_liquidity_with_pipeline(symbol, stage2)
    
    result.stage2 = stage2
    result.stage_reached = EvaluationStage.STAGE2_CHAIN
    
    # EOD OPTIONS STRATEGY WAIVER:
    # If we have valid option chain liquidity, waive stock bid/ask/volume requirements
    # These fields are intraday-only and not needed for EOD options strategies
    STOCK_INTRADAY_FIELDS = {"bid", "ask", "volume", "bidsize", "asksize"}
    
    if stage2.liquidity_ok:
        # Remove stock intraday fields from missing_fields - we have options liquidity
        original_missing = result.missing_fields.copy()
        result.missing_fields = [
            f for f in result.missing_fields 
            if f.lower() not in STOCK_INTRADAY_FIELDS
        ]
        waived_fields = [f for f in original_missing if f.lower() in STOCK_INTRADAY_FIELDS]
        
        if waived_fields:
            # Recalculate data completeness without the waived fields
            result.data_completeness = min(1.0, result.data_completeness + 0.1 * len(waived_fields))
            result.data_completeness = min(1.0, result.data_completeness)
            
            # Add gate showing the waiver; OPRA is sole liquidity authority
            result.gates.append({
                "name": "EOD Strategy Data Waiver",
                "status": "WAIVED",
                "reason": f"Stock {', '.join(waived_fields)} waived - options liquidity confirmed (DERIVED_FROM_OPRA)",
            })
            logger.info(
                "[EOD_WAIVER] %s: waived stock fields %s because OPRA liquidity valid (DERIVED_FROM_OPRA)",
                symbol, waived_fields
            )
        # OPRA is sole liquidity authority: attach waiver reason whenever OPRA gate passed
        result.waiver_reason = "DERIVED_FROM_OPRA"
        valid_contracts = getattr(stage2, "opra_valid_contracts", None)
        logger.info(
            "OPRA waiver applied symbol=%s valid_contracts=%s",
            symbol, valid_contracts,
        )
    
    # Add stage 2 gate
    result.gates.append({
        "name": "Options Liquidity (Stage 2)",
        "status": "PASS" if stage2.liquidity_ok else "FAIL",
        "reason": stage2.liquidity_reason,
    })
    
    result.liquidity_ok = stage2.liquidity_ok
    result.liquidity_reason = stage2.liquidity_reason
    result.options_available = stage2.expirations_available > 0
    result.options_reason = f"{stage2.expirations_evaluated} expirations evaluated" if stage2.expirations_evaluated > 0 else "No expirations"
    
    # Do NOT re-add missing fields or downgrade data_completeness when OPRA passed (no secondary veto)
    if stage2.chain_missing_fields and not stage2.liquidity_ok:
        result.missing_fields.extend(stage2.chain_missing_fields)
        result.data_completeness = min(result.data_completeness, stage2.chain_completeness)
    
    # Build candidate trade if contract selected
    if stage2.selected_contract and stage2.selected_expiration:
        contract = stage2.selected_contract.contract
        result.candidate_trades.append({
            "strategy": "CSP",
            "expiry": stage2.selected_expiration.isoformat(),
            "strike": contract.strike,
            "delta": contract.delta.value if contract.delta.is_valid else None,
            "credit_estimate": contract.bid.value if contract.bid.is_valid else None,
            "max_loss": (contract.strike * 100) - ((contract.bid.value or 0) * 100) if contract.bid.is_valid else None,
            "why_this_trade": stage2.selected_contract.selection_reason,
            "liquidity_grade": contract.get_liquidity_grade().value,
        })
    
    # Determine final verdict
    # Check for ELIGIBLE: either selected_contract exists OR liquidity was confirmed via enhancement
    is_enhanced = "(enhanced)" in (stage2.liquidity_reason or "")
    
    if stage2.liquidity_ok and stage2.selected_contract:
        # Standard path: contract selected from chain provider
        result.final_verdict = FinalVerdict.ELIGIBLE
        result.verdict = "ELIGIBLE"
        result.primary_reason = f"Chain evaluated, contract selected: {stage2.selected_contract.selection_reason}"
    elif stage2.liquidity_ok and is_enhanced:
        # OPRA path: liquidity from /datav2/strikes/options - sole authority; never DATA_INCOMPLETE
        result.final_verdict = FinalVerdict.ELIGIBLE
        result.verdict = "ELIGIBLE"
        result.primary_reason = f"Options liquidity confirmed (DERIVED_FROM_OPRA): {stage2.liquidity_reason}"
        if not result.waiver_reason:
            result.waiver_reason = "DERIVED_FROM_OPRA"
        logger.info("[VERDICT] %s: ELIGIBLE via OPRA liquidity (DERIVED_FROM_OPRA)", symbol)
    elif stage2.error:
        result.final_verdict = FinalVerdict.UNKNOWN
        result.verdict = "UNKNOWN"
        result.primary_reason = f"Chain evaluation error: {stage2.error}"
        result.error = stage2.error
    elif stage2.chain_missing_fields:
        # DATA_INCOMPLETE only when OPRA failed or returned zero valid contracts (liquidity_ok is False)
        result.final_verdict = FinalVerdict.HOLD
        result.verdict = "HOLD"
        result.primary_reason = f"DATA_INCOMPLETE: missing {', '.join(stage2.chain_missing_fields)}"
    else:
        result.final_verdict = FinalVerdict.HOLD
        result.verdict = "HOLD"
        result.primary_reason = stage2.liquidity_reason or "No suitable contract found"
    
    # Compute final score (legacy formula)
    result.score = _compute_final_score(result)
    result.confidence = _compute_confidence(result)
    
    # Phase 3: Score breakdown so single-symbol callers (e.g. Ticker) get it; batch overwrites after gates.
    put_strike = None
    if result.stage2 and result.stage2.selected_contract:
        put_strike = result.stage2.selected_contract.contract.strike
    try:
        breakdown, composite = compute_score_breakdown(
            data_completeness=result.data_completeness,
            regime=result.regime,
            liquidity_ok=result.liquidity_ok,
            liquidity_grade=result.stage2.liquidity_grade if result.stage2 else None,
            verdict=result.verdict,
            position_open=result.position_open,
            price=result.price,
            selected_put_strike=put_strike,
        )
        result.score = composite
        result.score_breakdown = breakdown.to_dict()
        result.rank_reasons = build_rank_reasons(
            breakdown, result.regime, result.data_completeness,
            result.liquidity_ok, result.verdict,
        )
        result.csp_notional = breakdown.csp_notional
        result.notional_pct = breakdown.notional_pct
    except Exception as e:
        logger.debug("[EVAL] Score breakdown for %s: %s", result.symbol, e)
    
    return result


def _compute_final_score(result: FullEvaluationResult) -> int:
    """Compute final score based on both stages."""
    base_score = result.stage1.stage1_score if result.stage1 else 50
    
    if result.stage_reached == EvaluationStage.STAGE1_ONLY:
        return base_score
    
    # Stage 2 adjustments
    if result.liquidity_ok:
        base_score += 15
    else:
        base_score -= 10
    
    if result.stage2 and result.stage2.selected_contract:
        base_score += 10
        # Liquidity grade bonus
        grade = result.stage2.liquidity_grade
        if grade == "A":
            base_score += 10
        elif grade == "B":
            base_score += 5
    
    # No secondary veto: when OPRA passed (liquidity_ok), do not cap score for data_completeness
    if result.data_completeness < 0.75 and not result.liquidity_ok:
        base_score = min(base_score, DATA_INCOMPLETE_SCORE_CAP)
    
    return max(0, min(100, base_score))


def _compute_confidence(result: FullEvaluationResult) -> float:
    """Compute confidence score based on data quality and stage reached."""
    base_confidence = 0.25  # Baseline
    
    if result.stage_reached == EvaluationStage.STAGE2_CHAIN:
        base_confidence += 0.25
    
    if result.price is not None:
        base_confidence += 0.15
    
    if result.liquidity_ok:
        base_confidence += 0.20
    
    if result.stage2 and result.stage2.selected_contract:
        base_confidence += 0.15
    
    # Factor in data completeness
    return min(1.0, base_confidence * (0.5 + result.data_completeness * 0.5))


# ============================================================================
# Batch Evaluation
# ============================================================================

def evaluate_universe_staged(
    symbols: List[str],
    top_k: int = STAGE1_TOP_K,
    max_stage2_concurrent: int = STAGE2_MAX_CONCURRENT,
    chain_provider: Optional[OratsChainProvider] = None,
) -> List[FullEvaluationResult]:
    """
    Run 2-stage evaluation across universe.
    
    1. Run stage 1 for all symbols
    2. Select top K candidates
    3. Run stage 2 for top K (with concurrency limits)
    
    Returns:
        List of FullEvaluationResult for all symbols
    """
    provider = chain_provider or get_chain_provider()
    results: Dict[str, FullEvaluationResult] = {}
    
    logger.info("[STAGED_EVAL] Starting 2-stage evaluation for %d symbols", len(symbols))
    start_time = time.time()
    
    # Phase 8D: Per-run ORATS cache — pre-fetch equity + ivrank for all symbols so stage1 uses cache
    try:
        from app.core.orats.orats_equity_quote import reset_run_cache, fetch_full_equity_snapshots
        reset_run_cache()
        pre = fetch_full_equity_snapshots(symbols)
        logger.info("[STAGED_EVAL] Pre-fetched equity snapshots for %d symbols (cache ready for stage1)", len(pre))
    except Exception as e:
        logger.warning("[STAGED_EVAL] Pre-fetch equity failed (stage1 will fetch per-symbol): %s", e)
    
    # Stage 1: Evaluate all symbols (cache hits for equity/ivrank)
    stage1_results: Dict[str, Stage1Result] = {}
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_symbol = {
            executor.submit(evaluate_stage1, symbol): symbol
            for symbol in symbols
        }
        
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                stage1_results[symbol] = future.result()
            except Exception as e:
                logger.exception("[STAGED_EVAL] Stage 1 error for %s: %s", symbol, e)
                stage1_results[symbol] = Stage1Result(
                    symbol=symbol,
                    stock_verdict=StockVerdict.ERROR,
                    stock_verdict_reason=f"Error: {e}",
                    error=str(e),
                )
    
    # Select top K candidates for stage 2
    qualified = [
        (symbol, s1) for symbol, s1 in stage1_results.items()
        if s1.stock_verdict == StockVerdict.QUALIFIED
    ]
    qualified.sort(key=lambda x: x[1].stage1_score, reverse=True)
    top_candidates = qualified[:top_k]
    
    logger.info(
        "[STAGED_EVAL] Stage 1 complete: %d qualified, advancing top %d to stage 2",
        len(qualified), len(top_candidates)
    )
    
    # Build results for non-qualified (stage 1 only)
    for symbol, stage1 in stage1_results.items():
        if symbol not in [s for s, _ in top_candidates]:
            result = FullEvaluationResult(symbol=symbol)
            result.stage1 = stage1
            result.stage_reached = EvaluationStage.STAGE1_ONLY
            result.price = stage1.price
            result.bid = stage1.bid
            result.ask = stage1.ask
            result.volume = stage1.volume
            result.avg_volume = stage1.avg_volume
            result.regime = stage1.regime
            result.risk = stage1.risk_posture
            result.data_completeness = stage1.data_completeness
            result.missing_fields = stage1.missing_fields
            result.data_quality_details = stage1.data_quality_details
            result.data_sources = stage1.data_sources
            result.raw_fields_present = stage1.raw_fields_present
            result.field_sources = getattr(stage1, "field_sources", {})
            result.quote_date = stage1.quote_date
            result.iv_rank = stage1.iv_rank
            result.score = stage1.stage1_score
            
            if stage1.stock_verdict == StockVerdict.BLOCKED:
                result.final_verdict = FinalVerdict.BLOCKED
                result.verdict = "BLOCKED"
            elif stage1.stock_verdict == StockVerdict.ERROR:
                result.final_verdict = FinalVerdict.UNKNOWN
                result.verdict = "UNKNOWN"
                result.error = stage1.error
            else:
                result.final_verdict = FinalVerdict.HOLD
                result.verdict = "HOLD"
            
            result.primary_reason = stage1.stock_verdict_reason
            result.options_available = False
            result.options_reason = "Not in top K candidates"
            results[symbol] = result
    
    # Stage 2: Evaluate top candidates with bounded concurrency
    with ThreadPoolExecutor(max_workers=max_stage2_concurrent) as executor:
        future_to_symbol = {}
        for symbol, stage1 in top_candidates:
            future = executor.submit(
                _run_full_evaluation_for_qualified,
                symbol, stage1, provider
            )
            future_to_symbol[future] = symbol
        
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                results[symbol] = future.result()
            except Exception as e:
                logger.exception("[STAGED_EVAL] Stage 2 error for %s: %s", symbol, e)
                # Fall back to stage 1 only
                stage1 = stage1_results[symbol]
                result = FullEvaluationResult(symbol=symbol)
                result.stage1 = stage1
                result.stage_reached = EvaluationStage.STAGE1_ONLY
                result.final_verdict = FinalVerdict.UNKNOWN
                result.verdict = "UNKNOWN"
                result.primary_reason = f"Stage 2 error: {e}"
                result.error = str(e)
                results[symbol] = result
    
    # Phase 7: Apply market regime gate (index-based). Cap scores and force HOLD when RISK_OFF.
    market_regime_value = "NEUTRAL"
    try:
        from app.core.market.market_regime import get_market_regime
        regime_snapshot = get_market_regime()
        market_regime_value = regime_snapshot.regime
        for result in results.values():
            result.regime = market_regime_value
            if market_regime_value == "RISK_OFF":
                result.score = min(result.score, 50)
                result.final_verdict = FinalVerdict.HOLD
                result.verdict = "HOLD"
                result.primary_reason = "Blocked by market regime: RISK_OFF"
            elif market_regime_value == "NEUTRAL":
                result.score = min(result.score, 65)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("[STAGED_EVAL] Market regime gate skipped: %s", e)

    # Phase 9: Position-aware evaluation and exposure control.
    from app.core.eval.position_awareness import (
        get_open_positions_by_symbol,
        get_exposure_summary,
        position_blocks_recommendation,
        check_exposure_limits,
        ExposureSummary,
    )
    open_by_symbol = get_open_positions_by_symbol()
    exposure_summary = get_exposure_summary(open_trades_by_symbol=open_by_symbol)
    for result in results.values():
        blocks, reason = position_blocks_recommendation(result.symbol, open_by_symbol, strategy_focus="CSP")
        if blocks:
            result.final_verdict = FinalVerdict.HOLD
            result.verdict = "HOLD"
            result.primary_reason = reason
            result.position_open = True
            result.position_reason = reason
        else:
            allowed, cap_reason = check_exposure_limits(result.symbol, exposure_summary, open_by_symbol)
            if not allowed and cap_reason:
                result.final_verdict = FinalVerdict.HOLD
                result.verdict = "HOLD"
                result.primary_reason = cap_reason
        if result.symbol in open_by_symbol:
            result.position_open = True
            if not result.position_reason:
                result.position_reason = "POSITION_ALREADY_OPEN"

    # Phase 3: Explainable scoring and capital-aware composite (after regime + position gates).
    for result in results.values():
        put_strike = None
        if result.stage2 and result.stage2.selected_contract:
            put_strike = result.stage2.selected_contract.contract.strike
        try:
            breakdown, composite = compute_score_breakdown(
                data_completeness=result.data_completeness,
                regime=result.regime,
                liquidity_ok=result.liquidity_ok,
                liquidity_grade=result.stage2.liquidity_grade if result.stage2 else None,
                verdict=result.verdict,
                position_open=result.position_open,
                price=result.price,
                selected_put_strike=put_strike,
            )
            if market_regime_value == "RISK_OFF":
                composite = min(composite, 50)
            elif market_regime_value == "NEUTRAL":
                composite = min(composite, 65)
            result.score = max(0, min(100, composite))
            result.score_breakdown = breakdown.to_dict()
            result.rank_reasons = build_rank_reasons(
                breakdown, result.regime, result.data_completeness,
                result.liquidity_ok, result.verdict,
            )
            result.csp_notional = breakdown.csp_notional
            result.notional_pct = breakdown.notional_pct
        except Exception as e:
            logger.debug("[STAGED_EVAL] Score breakdown for %s: %s", result.symbol, e)

    # Phase 8: Build strategy rationale for each result (human-readable verdict explanation).
    # Phase 10: Compute confidence band and capital hint for each result.
    for result in results.values():
        try:
            result.rationale = build_rationale_from_staged(
                symbol=result.symbol,
                verdict=result.verdict,
                primary_reason=result.primary_reason,
                stage1=result.stage1,
                stage2=result.stage2,
                market_regime=result.regime or market_regime_value,
                score=result.score,
                data_completeness=result.data_completeness,
                missing_fields=result.missing_fields,
                position_open=result.position_open,
                position_reason=result.position_reason,
            )
        except Exception as e:
            logger.debug("[STAGED_EVAL] Rationale build for %s: %s", result.symbol, e)
        try:
            result.capital_hint = compute_confidence_band(
                verdict=result.verdict,
                regime=result.regime,
                data_completeness=result.data_completeness,
                liquidity_ok=result.liquidity_ok,
                score=result.score,
                position_open=result.position_open,
            )
            result.band_reason = result.capital_hint.band_reason if result.capital_hint else None
        except Exception as e:
            logger.debug("[STAGED_EVAL] Confidence band for %s: %s", result.symbol, e)

    # Score normalization check: warn if all scores are identical (may indicate evaluation bug)
    all_scores = [r.score for r in results.values() if r.score > 0]
    if all_scores and len(set(all_scores)) == 1 and len(all_scores) > 1:
        logger.warning("[EVAL] score_flattened=true - all %d non-zero scores identical (%d)", len(all_scores), all_scores[0])

    duration = time.time() - start_time
    eligible_count = sum(1 for r in results.values() if r.final_verdict == FinalVerdict.ELIGIBLE)
    stage2_count = sum(1 for r in results.values() if r.stage_reached == EvaluationStage.STAGE2_CHAIN)
    
    logger.info(
        "[STAGED_EVAL] Complete: %d symbols, %d stage2, %d eligible, %.1fs",
        len(results), stage2_count, eligible_count, duration
    )
    return StagedEvaluationResult(results=list(results.values()), exposure_summary=exposure_summary)


def _run_full_evaluation_for_qualified(
    symbol: str,
    stage1: Stage1Result,
    provider: OratsChainProvider,
) -> FullEvaluationResult:
    """Run full evaluation for a qualified symbol."""
    result = evaluate_symbol_full(symbol, chain_provider=provider, skip_stage2=False)
    # Ensure stage1 is preserved
    result.stage1 = stage1
    return result


__all__ = [
    "EvaluationStage",
    "StockVerdict",
    "FinalVerdict",
    "Stage1Result",
    "Stage2Result",
    "FullEvaluationResult",
    "StagedEvaluationResult",
    "evaluate_stage1",
    "evaluate_stage2",
    "evaluate_symbol_full",
    "evaluate_universe_staged",
    "STAGE1_TOP_K",
    "STAGE2_MAX_CONCURRENT",
]
