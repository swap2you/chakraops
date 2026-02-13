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

import dataclasses
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.core.models.data_quality import build_data_incomplete_reason
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
from app.market.market_hours import get_stage2_chain_source
from app.core.config.wheel_strategy_config import (
    WHEEL_CONFIG,
    DTE_MIN,
    DTE_MAX,
    TARGET_DELTA_RANGE,
    MIN_UNDERLYING_VOLUME,
    MAX_UNDERLYING_SPREAD_PCT,
    MIN_OPTION_OI,
    MAX_OPTION_SPREAD_PCT,
    IVR_LOW,
    IVR_MID,
    IVR_HIGH,
    get_dte_range,
    get_target_delta_range,
    get_acquisition_delta_range,
    get_stage2_strategy_mode,
    USE_STAGE2_V2_ONLY,
)
from app.core.models.data_quality import wrap_field_float, wrap_field_int
from app.core.eval.volatility import get_ivr_band

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


# Configuration (Wheel strategy: from wheel_strategy_config, no hardcoded numbers)
STAGE1_TOP_K = 20  # Top K candidates to advance to stage 2
STAGE2_MAX_CONCURRENT = 5  # Max concurrent chain fetches
TARGET_DTE_MIN = WHEEL_CONFIG[DTE_MIN]
TARGET_DTE_MAX = WHEEL_CONFIG[DTE_MAX]
_delta_lo, _delta_hi = get_target_delta_range()
TARGET_DELTA = -(_delta_lo + _delta_hi) / 2  # Put delta (negative); use midpoint of range
DELTA_TOLERANCE = 0.10  # Tolerance around TARGET_DELTA for contract selection
MIN_LIQUIDITY_GRADE = ContractLiquidityGrade.B
MIN_OPEN_INTEREST = WHEEL_CONFIG[MIN_OPTION_OI]
MAX_SPREAD_PCT = WHEEL_CONFIG[MAX_OPTION_SPREAD_PCT]

# Scoring
SHORTLIST_SCORE_THRESHOLD = 70
DATA_INCOMPLETE_SCORE_CAP = 60

# Required chain fields for Wheel strategy (Phase 3.3.1). required_fields_present is True
# iff at least one PUT in the fetched chain has all of these non-null and numeric (computed
# from chain contracts before selection, NOT from selected_candidates).
REQUIRED_CHAIN_FIELDS = [
    "strike",
    "expiration",
    "bid",
    "ask",
    "delta",
    "open_interest",
]
# Phase 3.1: For selection eligibility, OI is optional (counted but null OI does not wipe candidates).
REQUIRED_CHAIN_FIELDS_FOR_SELECTION = ["strike", "expiration", "bid", "ask", "delta"]


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
    
    # Stock data (from canonical snapshot only; no avg_volume — use volume metrics from data_requirements)
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    avg_option_volume_20d: Optional[float] = None  # /datav2/cores avgOptVolu20d
    avg_stock_volume_20d: Optional[float] = None   # derived from /datav2/hist/dailies
    iv_rank: Optional[float] = None
    quote_date: Optional[str] = None  # quoteDate from ORATS
    
    # Stage 1 verdict
    stock_verdict: StockVerdict = StockVerdict.ERROR
    stock_verdict_reason: str = ""
    stage1_score: int = 0  # 0-100
    
    # Context (Phase 3.2.3: from IVR band only, no trend logic)
    regime: Optional[str] = None
    risk_posture: Optional[str] = None
    ivr_band: Optional[str] = None  # LOW | MID | HIGH from wheel config bands

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
    
    # Selected contract (Phase 3.2.4: top 1; selected_candidates holds 1–3)
    selected_contract: Optional[SelectedContract] = None
    selected_expiration: Optional[date] = None
    selected_candidates: List[Any] = field(default_factory=list)  # Up to 3 SelectedContract
    contract_selection_reasons: List[str] = field(default_factory=list)  # When no contract passes

    # Liquidity assessment
    liquidity_grade: Optional[str] = None
    liquidity_reason: str = ""
    liquidity_ok: bool = False
    
    # Chain data quality (computed from chain PUTs, not selected_candidates)
    chain_completeness: float = 0.0
    chain_missing_fields: List[str] = field(default_factory=list)
    required_fields_present: bool = False  # At least one PUT in chain has all REQUIRED_CHAIN_FIELDS
    total_puts_in_chain: int = 0
    puts_with_required_fields: int = 0
    chain_source_used: Optional[str] = None  # LIVE | DELAYED from provider
    
    # Metadata
    chains_fetched_at: Optional[str] = None
    chain_fetch_duration_ms: int = 0
    error: Optional[str] = None
    # OPRA enhancement: count of valid contracts when liquidity_ok from strikes/options
    opra_valid_contracts: Optional[int] = None
    # Debug: rejection reason counts (lightweight trace for Stage-2 artifacts)
    rejection_counts: Dict[str, int] = field(default_factory=dict)
    # Option type counts from chain contracts (before filtering) for diagnostics
    option_type_counts: Dict[str, int] = field(default_factory=dict)  # puts_seen, calls_seen, unknown_seen
    # Delta distribution for PUTs in fetched chain (for diagnostics when contract unavailable)
    delta_distribution: Optional[Dict[str, Any]] = None  # min_abs_put_delta, max_abs_put_delta, sample_abs_deltas
    # Top rejection reasons with sample contracts (for diagnostics)
    top_rejection_reasons: Optional[Dict[str, Any]] = None  # rejection_counts + sample_rejected_due_to_delta
    # Missing required-fields diagnostics (30–45 DTE PUTs, same population as selection)
    missing_required_fields_counts: Dict[str, int] = field(default_factory=dict)  # field -> count of PUTs missing it
    sample_missing_required_contract: Optional[Dict[str, Any]] = None  # first rejected PUT: option_symbol (OCC), option_type, values_seen, raw_keys
    # Telemetry from /strikes/options (endpoint_used, non_null counts, sample symbols)
    strikes_options_telemetry: Optional[Dict[str, Any]] = None
    # Stage-2 trace (pipeline acquisition + samples) for validate_one_symbol / harness comparison
    stage2_trace: Optional[Dict[str, Any]] = None
    # Phase 3.1: OTM and delta-band counts (from chain + spot)
    otm_puts_in_dte: int = 0
    otm_puts_in_delta_band: int = 0
    spot_used: Optional[float] = None


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
    avg_option_volume_20d: Optional[float] = None
    avg_stock_volume_20d: Optional[float] = None
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
    
    # Phase 3.0.2: Split eligibility layers (symbol vs contract)
    symbol_eligibility: Optional[Dict[str, Any]] = None  # { status: PASS|FAIL, reasons: [] }
    contract_data: Optional[Dict[str, Any]] = None       # { available, as_of, source: LIVE|EOD_SNAPSHOT|NONE }
    contract_eligibility: Optional[Dict[str, Any]] = None  # { status: PASS|FAIL|UNAVAILABLE, reasons: [] }
    # Phase 3.2.2: Explicit liquidity gate results (underlying + option) for artifact
    liquidity_gates: Optional[Dict[str, Any]] = None  # { underlying: {...}, option: {...} }
    # Phase 4: Eligibility gate trace (mode_decision CSP | CC | NONE)
    eligibility_trace: Optional[Dict[str, Any]] = None

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
            "avg_option_volume_20d": self.avg_option_volume_20d,
            "avg_stock_volume_20d": self.avg_stock_volume_20d,
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
            "symbol_eligibility": self.symbol_eligibility,
            "contract_data": self.contract_data,
            "contract_eligibility": self.contract_eligibility,
            "liquidity_gates": self.liquidity_gates,
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

    Uses ONLY canonical snapshot (symbol_snapshot_service). Delayed data only; no live.
    Stage-1 HARD GATE: any required field missing or stale → BLOCK.
    """
    from app.core.data.symbol_snapshot_service import get_snapshot
    from app.core.data.contract_validator import validate_equity_snapshot
    from app.core.data.data_requirements import (
        REQUIRED_STAGE1_FIELDS,
        STAGE1_STALE_TRADING_DAYS,
    )
    from app.core.environment.market_calendar import trading_days_since
    from app.core.data.orats_client import FullEquitySnapshot

    result = Stage1Result(symbol=symbol, source="ORATS")
    now_iso = datetime.now(timezone.utc).isoformat()
    result.fetched_at = now_iso

    try:
        # Canonical snapshot only (delayed strikes/options + cores + optional derived)
        canonical = get_snapshot(symbol, derive_avg_stock_volume_20d=True, use_cache=True)

        # Adapter: validator expects FullEquitySnapshot
        snapshot = FullEquitySnapshot(
            symbol=symbol.upper(),
            price=canonical.price,
            bid=canonical.bid,
            ask=canonical.ask,
            volume=canonical.volume,
            quote_date=canonical.quote_date,
            iv_rank=canonical.iv_rank,
            data_sources=dict(canonical.field_sources),
            raw_fields_present=[],
            missing_fields=list(canonical.missing_reasons.keys()),
            missing_reasons=dict(canonical.missing_reasons),
        )

        # Single validator: instrument type + required fields + derivations
        validation = validate_equity_snapshot(symbol, snapshot)

        result.price = validation.price
        result.bid = validation.bid
        result.ask = validation.ask
        result.volume = validation.volume
        result.avg_option_volume_20d = canonical.avg_option_volume_20d
        result.avg_stock_volume_20d = canonical.avg_stock_volume_20d
        result.iv_rank = validation.iv_rank
        result.quote_date = validation.quote_date
        result.data_completeness = validation.data_completeness
        result.missing_fields = validation.missing_fields.copy()
        result.data_quality_details = validation.data_quality_details.copy()
        result.field_sources = validation.field_sources.copy()
        result.data_sources = snapshot.data_sources.copy()
        result.raw_fields_present = snapshot.raw_fields_present.copy()

        # Stage-1 HARD GATE: any required field missing → BLOCK
        if result.missing_fields:
            result.stock_verdict = StockVerdict.BLOCKED
            result.stock_verdict_reason = f"DATA_INCOMPLETE: required missing ({', '.join(result.missing_fields)})"
            logger.warning("[STAGE1] %s BLOCKED: required missing %s", symbol, result.missing_fields)
            return result

        # Stage-1 HARD GATE: stale → BLOCK (no WARN + PASS)
        quote_date_parsed = None
        if result.quote_date:
            try:
                from datetime import date
                s = str(result.quote_date).strip()[:10]
                if len(s) >= 10:
                    quote_date_parsed = date(int(s[:4]), int(s[5:7]), int(s[8:10]))
            except (ValueError, IndexError):
                pass
        if quote_date_parsed:
            days = trading_days_since(quote_date_parsed)
            if days is not None and days > STAGE1_STALE_TRADING_DAYS:
                result.stock_verdict = StockVerdict.BLOCKED
                result.stock_verdict_reason = f"DATA_STALE: quote_date {result.quote_date} is {days} trading days old"
                logger.warning("[STAGE1] %s BLOCKED: data stale (%s days)", symbol, days)
                return result

        if validation.price is None:
            result.stock_verdict = StockVerdict.BLOCKED
            result.stock_verdict_reason = "DATA_INCOMPLETE_FATAL: No price data"
            return result

        logger.debug(
            "[SNAPSHOT] %s: price=%s bid=%s ask=%s volume=%s iv_rank=%s sources=%s",
            symbol, result.price, result.bid, result.ask, result.volume,
            result.iv_rank, result.data_sources,
        )
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

        # Phase 3.2.3: Regime from IV Rank bands only (no trend logic)
        result.ivr_band = get_ivr_band(result.iv_rank)
        if result.ivr_band == IVR_LOW:
            result.regime = "LOW_VOL"
            result.risk_posture = "LOW"
        elif result.ivr_band == IVR_MID:
            result.regime = "NEUTRAL"
            result.risk_posture = "MODERATE"
        elif result.ivr_band == IVR_HIGH:
            result.regime = "HIGH_VOL"
            result.risk_posture = "HIGH"
        else:
            result.regime = "UNKNOWN"
            result.risk_posture = "UNKNOWN"

        # Compute stage 1 score
        result.stage1_score = _compute_stage1_score(result)
        
        # Qualified for stage 2
        result.stock_verdict = StockVerdict.QUALIFIED
        result.stock_verdict_reason = f"Stock qualified (score: {result.stage1_score})"
        
    except Exception as e:
        logger.exception("[STAGE1] Error evaluating %s: %s", symbol, e)
        result.stock_verdict = StockVerdict.ERROR
        result.stock_verdict_reason = f"Evaluation error: {e}"
        result.error = str(e)

    return result


def _compute_stage1_score(result: Stage1Result) -> int:
    """Compute stage 1 score: IVR band only — LOW penalize, MID neutral, HIGH positive (Phase 3.2.3)."""
    score = 50  # Baseline

    # IV Rank band scoring (no trend logic)
    if result.ivr_band == IVR_LOW:
        score -= 15  # Penalize: low premium environment
    elif result.ivr_band == IVR_MID:
        pass  # Neutral
    elif result.ivr_band == IVR_HIGH:
        score += 10  # Positive: favorable premium (tail risk note added in rationale)

    # Data completeness factor
    score = int(score * result.data_completeness)
    
    # Cap if incomplete
    if result.data_completeness < 0.75:
        score = min(score, DATA_INCOMPLETE_SCORE_CAP)
    
    return max(0, min(100, score))


# ============================================================================
# Stage 2: Contract selection (Phase 3.2.4)
# ============================================================================

# Top N candidates to keep (1–3)
CONTRACT_SELECTION_TOP_N = 3


def _delta_magnitude(contract: OptionContract) -> Optional[float]:
    """Return |delta| for range checks; ORATS may return put deltas as positive or negative."""
    if not getattr(contract.delta, "is_valid", False) or contract.delta.value is None:
        return None
    try:
        return abs(float(contract.delta.value))
    except (TypeError, ValueError):
        return None


def _normalized_delta(contract: OptionContract) -> Optional[float]:
    """Puts: negative magnitude. Calls: positive magnitude. For reporting/storage."""
    mag = _delta_magnitude(contract)
    if mag is None:
        return None
    return -mag if contract.option_type == OptionType.PUT else mag


def _select_csp_candidates(
    chains: Dict[date, Any],
    dte_min: int,
    dte_max: int,
    delta_lo: float,
    delta_hi: float,
    min_oi: int,
    max_spread_pct: float,
    symbol: str,
) -> Tuple[List[SelectedContract], List[str], Dict[str, int], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filter by option_type==PUT, 30–45 DTE, then required fields, delta, OI, spread.
    Order: (a) required fields, (b) delta, (c) OI, (d) spread. Missing fields never masquerade as low OI.
    """
    reasons: List[str] = []
    rejection_counts: Dict[str, int] = {
        "rejected_due_to_wrong_type": 0,
        "rejected_due_to_delta": 0,
        "rejected_due_to_oi": 0,
        "rejected_due_to_spread": 0,
        "rejected_due_to_missing_fields": 0,
        "rejected_due_to_itm": 0,
    }
    sample_rejected_due_to_delta: List[Dict[str, Any]] = []

    # Spot from first chain (for OTM gating)
    spot: Optional[float] = None
    for chain_result in chains.values():
        if chain_result.success and chain_result.chain and chain_result.chain.underlying_price is not None:
            uv = chain_result.chain.underlying_price
            if getattr(uv, "value", None) is not None:
                spot = float(uv.value)
                break

    # Collect put contracts from chains in DTE range; count wrong_type (CALL in CSP pool)
    all_puts: List[Tuple[OptionContract, date]] = []
    for exp_date, chain_result in chains.items():
        if not chain_result.success or chain_result.chain is None:
            continue
        chain = chain_result.chain
        for c in chain.contracts:
            if not (dte_min <= c.dte <= dte_max):
                continue
            if c.option_type != OptionType.PUT:
                rejection_counts["rejected_due_to_wrong_type"] += 1
                continue
            c.compute_derived_fields()
            all_puts.append((c, exp_date))

    if not all_puts:
        reasons.append("No contracts in 30–45 DTE range")
        return [], reasons, rejection_counts, sample_rejected_due_to_delta, []

    # Phase 3.1: OTM gate — CSP (sell PUT): OTM means strike < spot. Filter before other gates.
    otm_puts: List[Tuple[OptionContract, date]] = []
    for c, exp in all_puts:
        if spot is not None and c.strike >= spot:
            rejection_counts["rejected_due_to_itm"] += 1
            continue
        otm_puts.append((c, exp))

    if not otm_puts:
        reasons.append("No OTM puts (strike < spot)" if spot is not None else "No puts after filters")
        return [], reasons, rejection_counts, sample_rejected_due_to_delta, []

    # Apply filters in order: (a) required fields (bid/ask/delta; OI optional), (b) delta, (c) OI, (d) spread
    passed: List[Tuple[OptionContract, date]] = []
    for c, exp in otm_puts:
        # (a) Required fields for selection (no OI) — missing -> rejected_due_to_missing_fields
        has_all, _ = _contract_has_required_fields_for_selection(c)
        if not has_all:
            rejection_counts["rejected_due_to_missing_fields"] += 1
            continue
        # (b) Delta filter (abs(delta) in band 0.20–0.40)
        delta_mag = _delta_magnitude(c)
        if delta_mag is None:
            rejection_counts["rejected_due_to_missing_fields"] += 1
            continue
        if not (delta_lo <= delta_mag <= delta_hi):
            rejection_counts["rejected_due_to_delta"] += 1
            if len(sample_rejected_due_to_delta) < 3:
                sample_rejected_due_to_delta.append({
                    "strike": c.strike,
                    "expiration": exp.isoformat(),
                    "abs_delta": round(delta_mag, 4),
                    "option_type": getattr(c.option_type, "value", str(c.option_type)),
                })
            continue
        # (c) OI filter - OI is valid numeric at this point (required-field check passed)
        _, oi_val = _is_valid_numeric_field(getattr(c, "open_interest", None))
        oi = int(oi_val) if oi_val is not None else 0
        if oi < min_oi:
            rejection_counts["rejected_due_to_oi"] += 1
            continue
        # (d) Spread filter
        _, sp_val = _is_valid_numeric_field(getattr(c, "spread_pct", None))
        sp = float(sp_val) if sp_val is not None else 1.0
        if sp > max_spread_pct:
            rejection_counts["rejected_due_to_spread"] += 1
            continue
        passed.append((c, exp))

    if not passed:
        reasons.append(f"No contracts passed option liquidity gates (OI≥{min_oi}, spread≤{max_spread_pct:.0%})")
        sample_rejected_candidates = []
        for c, _ in otm_puts[:10]:
            _, bid_v = _is_valid_numeric_field(getattr(c, "bid", None))
            _, ask_v = _is_valid_numeric_field(getattr(c, "ask", None))
            _, oi_v = _is_valid_numeric_field(getattr(c, "open_interest", None))
            sample_rejected_candidates.append({
                "strike": c.strike,
                "abs_delta": round(_delta_magnitude(c) or 0, 4),
                "bid": bid_v,
                "ask": ask_v,
                "oi": int(oi_v) if oi_v is not None else None,
            })
        return [], reasons, rejection_counts, sample_rejected_due_to_delta, sample_rejected_candidates

    # Rank by premium/capital_required and liquidity quality
    def rank_key(item: Tuple[OptionContract, date]) -> Tuple[float, int]:
        c, _ = item
        capital = (c.strike * 100) if c.strike and c.strike > 0 else 1
        bid_val = c.bid.value if c.bid.is_valid and c.bid.value is not None else 0
        premium_cap = bid_val / capital if capital else 0
        grade = c.get_liquidity_grade()
        grade_order = {"A": 3, "B": 2, "C": 1, "D": 0, "F": 0}.get(grade.value, 0)
        return (premium_cap, grade_order)

    passed.sort(key=rank_key, reverse=True)
    top = passed[:CONTRACT_SELECTION_TOP_N]

    # Build SelectedContract list; report normalized delta (negative for puts)
    candidates: List[SelectedContract] = []
    for c, exp_date in top:
        reason_parts = []
        norm_d = _normalized_delta(c)
        if norm_d is not None:
            reason_parts.append(f"delta={norm_d:.2f}")
        reason_parts.append(f"DTE={c.dte}")
        reason_parts.append(f"grade={c.get_liquidity_grade().value}")
        if c.bid.is_valid and c.bid.value is not None:
            reason_parts.append(f"bid=${c.bid.value:.2f}")
        sel = SelectedContract(
            contract=c,
            selection_reason=", ".join(reason_parts),
            meets_all_criteria=True,
            criteria_results={"dte_in_range": True, "liquidity_ok": True},
        )
        candidates.append(sel)
    return candidates, [], rejection_counts, sample_rejected_due_to_delta, []


def _is_valid_numeric_field(field_value: Any) -> Tuple[bool, Optional[float]]:
    """
    Return (True, numeric) only if the field exists AND is numeric AND not NaN.
    Return (False, None) if missing/invalid. Do NOT coerce invalid to 0.
    """
    if field_value is None:
        return (False, None)
    # Handle FieldValue wrapper
    val = getattr(field_value, "value", field_value)
    if val is None:
        return (False, None)
    if not isinstance(val, (int, float)):
        return (False, None)
    if isinstance(val, float) and math.isnan(val):
        return (False, None)
    return (True, float(val))


def _contract_has_all_required_chain_fields(contract: OptionContract) -> Tuple[bool, List[str]]:
    """
    Return (True, []) if all REQUIRED_CHAIN_FIELDS are present and valid numeric.
    Uses _is_valid_numeric_field: missing/invalid -> fail; present numeric (including OI=0) -> pass.
    Liquidity thresholds (OI>=500) are applied separately in selection.
    """
    missing: List[str] = []
    for fn in REQUIRED_CHAIN_FIELDS:
        if fn == "strike":
            ok, _ = _is_valid_numeric_field(contract.strike)
            if not ok:
                missing.append(fn)
            continue
        if fn == "expiration":
            if contract.expiration is None:
                missing.append(fn)
            continue
        fv = getattr(contract, fn, None)
        if fv is None:
            missing.append(fn)
            continue
        ok, _ = _is_valid_numeric_field(fv)
        if not ok:
            missing.append(fn)
    return (len(missing) == 0, missing)


def _contract_has_required_fields_for_selection(contract: OptionContract) -> Tuple[bool, List[str]]:
    """Phase 3.1: Required for CSP/CC selection (bid, ask, delta, strike, expiration). OI optional."""
    missing: List[str] = []
    for fn in REQUIRED_CHAIN_FIELDS_FOR_SELECTION:
        if fn == "strike":
            ok, _ = _is_valid_numeric_field(contract.strike)
            if not ok:
                missing.append(fn)
            continue
        if fn == "expiration":
            if contract.expiration is None:
                missing.append(fn)
            continue
        fv = getattr(contract, fn, None)
        if fv is None:
            missing.append(fn)
            continue
        ok, _ = _is_valid_numeric_field(fv)
        if not ok:
            missing.append(fn)
    return (len(missing) == 0, missing)


def _compute_required_chain_fields_from_candidates(
    selected_candidates: List[Any],
    current_chain_missing: List[str],
) -> Tuple[bool, List[str]]:
    """
    Legacy: compute from selected_candidates. Prefer _compute_required_fields_from_chain_puts
    for required_fields_present (chain completeness).
    """
    if not selected_candidates:
        return False, current_chain_missing
    all_missing: set = set()
    for sc in selected_candidates:
        contract = getattr(sc, "contract", None)
        if contract is None:
            continue
        ok, missing = _contract_has_all_required_chain_fields(contract)
        if ok:
            return True, []
        all_missing.update(missing)
    return False, list(all_missing)


def _compute_required_fields_from_chain_puts(
    chains: Dict[date, Any],
) -> Tuple[bool, List[str], int, int]:
    """
    From chain PUTs: required = strike, expiration, delta, bid, ask (OI optional).
    required_fields_present = at least one PUT has all five. puts_with_required_fields = count with all five.
    Returns (required_fields_present, chain_missing_fields, total_puts, puts_with_required_fields).
    """
    put_contracts: List[OptionContract] = []
    for chain_result in chains.values():
        if not chain_result.success or chain_result.chain is None:
            continue
        for c in chain_result.chain.contracts:
            if c.option_type == OptionType.PUT:
                put_contracts.append(c)
    total_puts = len(put_contracts)
    puts_with_required = 0
    all_missing: set = set()
    for c in put_contracts:
        ok, missing = _contract_has_required_fields_for_selection(c)
        if ok:
            puts_with_required += 1
        all_missing.update(missing)
    required_fields_present = puts_with_required > 0
    return (required_fields_present, list(all_missing), total_puts, puts_with_required)


def _collect_puts_in_dte_range(
    chains: Dict[date, Any],
    dte_min: int,
    dte_max: int,
) -> List[Tuple[OptionContract, date]]:
    """
    Collect PUT contracts in 30–45 DTE from chains (exact same population as _select_csp_candidates).
    """
    all_puts: List[Tuple[OptionContract, date]] = []
    for exp_date, chain_result in chains.items():
        if not chain_result.success or chain_result.chain is None:
            continue
        chain = chain_result.chain
        for c in chain.contracts:
            if c.option_type != OptionType.PUT:
                continue
            if not (dte_min <= c.dte <= dte_max):
                continue
            c.compute_derived_fields()
            all_puts.append((c, exp_date))
    return all_puts


def _contract_values_seen(contract: OptionContract) -> Dict[str, Any]:
    """Extract values for REQUIRED_CHAIN_FIELDS from an OptionContract (for diagnostics)."""
    values: Dict[str, Any] = {}
    for fn in REQUIRED_CHAIN_FIELDS:
        if fn == "strike":
            values[fn] = getattr(contract, "strike", None)
            continue
        if fn == "expiration":
            exp = getattr(contract, "expiration", None)
            values[fn] = exp.isoformat() if exp else None
            continue
        fv = getattr(contract, fn, None)
        if fv is None:
            values[fn] = None
            continue
        val = getattr(fv, "value", fv)
        values[fn] = val
    return values


def _contract_raw_keys(contract: OptionContract) -> List[str]:
    """Return list of attribute names on OptionContract (for diagnostics)."""
    return [f.name for f in dataclasses.fields(contract)]


def _compute_missing_required_fields_diagnostics(
    puts_in_dte: List[Tuple[OptionContract, date]],
) -> Tuple[Dict[str, int], Optional[Dict[str, Any]]]:
    """
    For PUTs in 30–45 DTE: missing counts for required set (strike, expiration, delta, bid, ask) only.
    Returns (missing_required_fields_counts, sample_missing_required_contract).
    """
    missing_counts: Dict[str, int] = {f: 0 for f in REQUIRED_CHAIN_FIELDS_FOR_SELECTION}
    sample: Optional[Dict[str, Any]] = None
    for c, exp_date in puts_in_dte:
        has_all, missing_list = _contract_has_required_fields_for_selection(c)
        for f in missing_list:
            missing_counts[f] = missing_counts.get(f, 0) + 1
        if not has_all and sample is None:
            option_symbol = getattr(c, "option_symbol", None) or getattr(c, "symbol", None) or ""
            option_type = getattr(getattr(c, "option_type", None), "value", str(getattr(c, "option_type", "")))
            sample = {
                "option_symbol": option_symbol,
                "option_type": option_type,
                "values_seen": _contract_values_seen(c),
                "raw_keys": _contract_raw_keys(c),
            }
    return missing_counts, sample


# ============================================================================
# Stage 2: Chain Evaluation
# ============================================================================

def evaluate_stage2(
    symbol: str,
    stage1: Stage1Result,
    chain_provider: Optional[OratsChainProvider] = None,
    strategy_mode: str = "CSP",
) -> Stage2Result:
    """
    Stage 2: Fetch chains and evaluate contracts.
    
    Finds expirations in target DTE range and selects best contract.
    """
    result = Stage2Result(symbol=symbol)
    now_iso = datetime.now(timezone.utc).isoformat()
    result.chains_fetched_at = now_iso

    # Stage-2 MUST use DELAYED chain (strikes + strikes/options) for per-contract option_type/delta/OI.
    provider = chain_provider or get_chain_provider(chain_source=get_stage2_chain_source())
    chain_source_used = getattr(provider, "_chain_source", "DELAYED")
    result.chain_source_used = chain_source_used
    try:
        from app.market.market_hours import get_market_phase
        market_phase = get_market_phase()
        logger.info("[STAGE2_MODE] market_phase=%s chain_source=%s", market_phase, chain_source_used)
    except Exception:
        logger.info("[STAGE2_MODE] market_phase=UNKNOWN chain_source=%s", chain_source_used)
    start_time = time.time()
    
    try:
        # Phase 3.2.4: Filter expirations 30–45 DTE (wheel config)
        dte_min = WHEEL_CONFIG[DTE_MIN]
        dte_max = WHEEL_CONFIG[DTE_MAX]
        delta_lo, delta_hi = get_target_delta_range()
        min_oi = WHEEL_CONFIG[MIN_OPTION_OI]
        max_spread_pct = WHEEL_CONFIG[MAX_OPTION_SPREAD_PCT]

        # Phase 3.6/3.7: V2 ONLY — CSP and CC route to v2 engines. No legacy path.
        if USE_STAGE2_V2_ONLY:
            spot_used = getattr(stage1, "price", None)
            if spot_used is None:
                result.error = "TRACE_MISSING_BUG"
                result.liquidity_reason = "V2 requires spot_used (stage1.price); missing"
                result.stage2_trace = {"mode": (strategy_mode or "CSP"), "error": "TRACE_MISSING_BUG", "message": "spot_used required", "spot_used": None}
                result.chain_fetch_duration_ms = int((time.time() - start_time) * 1000)
                return result

            mode = (strategy_mode or get_stage2_strategy_mode()) or "CSP"
            from app.core.options.v2 import run_csp_stage2_v2, run_cc_stage2_v2

            if mode == "CC":
                v2_result = run_cc_stage2_v2(
                    symbol=symbol,
                    spot_used=float(spot_used),
                    snapshot_time=now_iso,
                    quote_as_of=getattr(stage1, "quote_date", None) or getattr(stage1, "quote_as_of", None),
                    dte_min=dte_min,
                    dte_max=dte_max,
                )
                option_type = OptionType.CALL
                delta_sign = 1.0
            else:
                v2_result = run_csp_stage2_v2(
                    symbol=symbol,
                    spot_used=float(spot_used),
                    snapshot_time=now_iso,
                    quote_as_of=getattr(stage1, "quote_date", None) or getattr(stage1, "quote_as_of", None),
                    dte_min=dte_min,
                    dte_max=dte_max,
                )
                option_type = OptionType.PUT
                delta_sign = -1.0

            result.chain_fetch_duration_ms = int((time.time() - start_time) * 1000)
            result.stage2_trace = v2_result.stage2_trace
            if not v2_result.stage2_trace:
                result.error = "TRACE_MISSING_BUG"
                result.liquidity_reason = "V2 returned no stage2_trace"
                result.stage2_trace = {"mode": mode, "error": "TRACE_MISSING_BUG", "message": "V2 must always return full trace"}
                return result

            trace = v2_result.stage2_trace
            req = trace.get("request_counts") or {}
            result.spot_used = v2_result.spot_used
            result.expirations_available = trace.get("expirations_count") or 0
            result.contracts_evaluated = v2_result.contract_count
            result.otm_puts_in_dte = trace.get("otm_puts_in_dte") or trace.get("otm_contracts_in_dte") or 0
            result.otm_puts_in_delta_band = trace.get("otm_puts_in_delta_band") or trace.get("otm_contracts_in_delta_band") or 0
            result.puts_with_required_fields = trace.get("puts_with_required_fields") or 0
            result.required_fields_present = (result.puts_with_required_fields > 0) or (trace.get("calls_with_required_fields", 0) > 0)
            result.total_puts_in_chain = v2_result.contract_count if mode == "CSP" else 0
            result.option_type_counts = {
                "puts_seen": req.get("puts_requested", 0),
                "calls_seen": req.get("calls_requested", 0),
                "unknown_seen": 0,
            }
            result.rejection_counts = trace.get("rejection_counts") or trace.get("rejected_counts") or {}
            result.top_rejection_reasons = {
                "rejection_counts": result.rejection_counts,
                "sample_rejected_candidates": v2_result.sample_rejections,
                "top_rejection_reason": v2_result.top_rejection or v2_result.top_rejection_reason,
            }
            result.strikes_options_telemetry = {
                "response_rows": trace.get("response_rows"),
                "puts_requested": req.get("puts_requested", 0),
                "calls_requested": req.get("calls_requested", 0),
                "sample_request_symbols": trace.get("sample_request_symbols"),
            }
            result.liquidity_ok = v2_result.success
            result.liquidity_reason = (
                f"delta={v2_result.selected_trade.get('abs_delta')}, bid=${v2_result.selected_trade.get('bid')}"
                if v2_result.selected_trade else (v2_result.top_rejection or v2_result.top_rejection_reason or "No contract selected")
            )
            if v2_result.selected_trade:
                st = v2_result.selected_trade
                exp_raw = st.get("exp")
                try:
                    exp_date = datetime.strptime(str(exp_raw)[:10], "%Y-%m-%d").date() if exp_raw else date.today()
                except (ValueError, TypeError):
                    exp_date = date.today()
                abs_delta = st.get("abs_delta")
                delta_val = (delta_sign * abs(float(abs_delta))) if abs_delta is not None else None
                oc = OptionContract(
                    symbol=symbol,
                    expiration=exp_date,
                    strike=float(st.get("strike", 0)),
                    option_type=option_type,
                    option_symbol=None,
                    bid=wrap_field_float(st.get("bid"), "bid"),
                    ask=wrap_field_float(st.get("ask"), "ask"),
                    delta=wrap_field_float(delta_val, "delta"),
                    open_interest=wrap_field_int(st.get("oi"), "open_interest"),
                    dte=0,
                )
                oc.compute_derived_fields()
                sel_reason = f"delta={abs_delta}, DTE=30-45, bid=${st.get('bid')} ({mode} V2)"
                result.selected_contract = SelectedContract(contract=oc, selection_reason=sel_reason, meets_all_criteria=True, criteria_results={})
                result.selected_expiration = exp_date
                result.selected_candidates = [result.selected_contract]
                result.liquidity_grade = "B"
            else:
                result.contract_selection_reasons = [v2_result.top_rejection or v2_result.top_rejection_reason or "No contract passed filters"]
            return result

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
            # required_fields_present/chain_missing_fields stay from chain PUTs (not overwritten)

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
# Liquidity gates (Phase 3.2.2)
# ============================================================================

def compute_underlying_liquidity_gates(stage1: Optional["Stage1Result"]) -> Dict[str, Any]:
    """
    Compute underlying liquidity gate results: spread_pct = (ask - bid) / price,
    enforce MIN_UNDERLYING_VOLUME and MAX_UNDERLYING_SPREAD_PCT.
    Returns dict with spread_pct, volume, min_volume_required, max_spread_pct_allowed,
    volume_ok, spread_ok, passed (all gates), reason (if failed).
    """
    min_vol = WHEEL_CONFIG[MIN_UNDERLYING_VOLUME]
    max_spread = WHEEL_CONFIG[MAX_UNDERLYING_SPREAD_PCT]
    out: Dict[str, Any] = {
        "spread_pct": None,
        "volume": None,
        "min_volume_required": min_vol,
        "max_spread_pct_allowed": max_spread,
        "volume_ok": False,
        "spread_ok": False,
        "passed": False,
        "reason": "Stage 1 not run",
    }
    if stage1 is None:
        return out
    # Volume: prefer avg_stock_volume_20d (config is "average daily share volume")
    vol = stage1.avg_stock_volume_20d
    if vol is None:
        vol = stage1.volume
    if vol is not None:
        try:
            vol_int = int(vol)
        except (TypeError, ValueError):
            vol_int = 0
    else:
        vol_int = None
    out["volume"] = vol_int
    out["volume_ok"] = (vol_int is not None and vol_int >= min_vol) if vol_int is not None else False
    # Spread: (ask - bid) / price
    bid, ask, price = stage1.bid, stage1.ask, stage1.price
    if bid is not None and ask is not None and price is not None and price > 0:
        spread_pct = (ask - bid) / price
        out["spread_pct"] = round(spread_pct, 6)
        out["spread_ok"] = spread_pct <= max_spread
    else:
        out["reason"] = "Missing bid, ask, or price for spread"
        return out
    out["passed"] = out["volume_ok"] and out["spread_ok"]
    if not out["volume_ok"]:
        out["reason"] = f"Volume {vol_int} < {min_vol}"
    elif not out["spread_ok"]:
        out["reason"] = f"Underlying spread {out['spread_pct']:.4%} > {max_spread:.4%}"
    else:
        out["reason"] = None
    return out


def compute_option_liquidity_gates(contract: Optional[Any]) -> Dict[str, Any]:
    """
    Compute option liquidity gate results: option_spread_pct = (ask - bid) / mid,
    enforce MIN_OPTION_OI and MAX_OPTION_SPREAD_PCT. contract is OptionContract or None.
    Returns dict with option_spread_pct, open_interest, min_oi_required,
    max_spread_pct_allowed, oi_ok, spread_ok, passed, reason.
    """
    min_oi = WHEEL_CONFIG[MIN_OPTION_OI]
    max_spread = WHEEL_CONFIG[MAX_OPTION_SPREAD_PCT]
    out: Dict[str, Any] = {
        "option_spread_pct": None,
        "open_interest": None,
        "min_oi_required": min_oi,
        "max_spread_pct_allowed": max_spread,
        "oi_ok": False,
        "spread_ok": False,
        "passed": False,
        "reason": "No selected contract",
    }
    if contract is None:
        return out
    # OptionContract has bid, ask, mid as FieldValue; also open_interest
    bid_val = contract.bid.value if getattr(contract.bid, "is_valid", False) and contract.bid.value is not None else None
    ask_val = contract.ask.value if getattr(contract.ask, "is_valid", False) and contract.ask.value is not None else None
    mid_val = contract.mid.value if getattr(contract.mid, "is_valid", False) and contract.mid.value is not None else None
    if mid_val is None and bid_val is not None and ask_val is not None:
        mid_val = (bid_val + ask_val) / 2
    oi_val = None
    if getattr(contract, "open_interest", None) is not None and getattr(contract.open_interest, "value", None) is not None:
        oi_val = contract.open_interest.value
    if oi_val is not None:
        try:
            oi_val = int(oi_val)
        except (TypeError, ValueError):
            oi_val = 0
    out["open_interest"] = oi_val
    out["oi_ok"] = (oi_val is not None and oi_val >= min_oi) if oi_val is not None else False
    # Ensure numeric types (avoid MagicMock or other mocks in tests)
    try:
        bid_f = float(bid_val) if bid_val is not None and isinstance(bid_val, (int, float)) else None
        ask_f = float(ask_val) if ask_val is not None and isinstance(ask_val, (int, float)) else None
        mid_f = float(mid_val) if mid_val is not None and isinstance(mid_val, (int, float)) else None
    except (TypeError, ValueError):
        bid_f = ask_f = mid_f = None
    if bid_f is not None and ask_f is not None and mid_f is not None and mid_f > 0:
        option_spread_pct = (ask_f - bid_f) / mid_f
        out["option_spread_pct"] = round(option_spread_pct, 6)
        out["spread_ok"] = option_spread_pct <= max_spread
    else:
        out["reason"] = "Missing bid, ask, or mid for option spread"
        return out
    out["passed"] = out["oi_ok"] and out["spread_ok"]
    if not out["oi_ok"]:
        out["reason"] = f"OI {oi_val} < {min_oi}"
    elif not out["spread_ok"]:
        out["reason"] = f"Option spread {out['option_spread_pct']:.4%} > {max_spread:.4%}"
    else:
        out["reason"] = None
    return out


# ============================================================================
# Eligibility layers (Phase 3.0.2)
# ============================================================================

def _merge_stage2_trace_with_rejections(
    stage2_trace: Optional[Dict[str, Any]],
    rejection_counts: Optional[Dict[str, int]],
) -> Optional[Dict[str, Any]]:
    """Return a copy of stage2_trace with rejection_counts merged (for validate_one_symbol artifact)."""
    if stage2_trace is None:
        return None
    import copy
    out = copy.deepcopy(stage2_trace)
    out["rejection_counts"] = dict(rejection_counts) if rejection_counts else {}
    return out


def _ensure_stage2_trace(
    stage2_trace: Optional[Dict[str, Any]],
    stage2: Optional[Any],
) -> Dict[str, Any]:
    """Phase 3.2: Never return null trace when contract_data exists. Return trace or minimal from stage2."""
    if isinstance(stage2_trace, dict) and stage2_trace:
        return stage2_trace
    minimal: Dict[str, Any] = {
        "spot_used": getattr(stage2, "spot_used", None),
        "expirations_in_window": getattr(stage2, "expirations_in_window", []) or [],
        "requested_put_strikes": getattr(stage2, "requested_put_strikes", None),
        "requested_tickers_count": None,
        "sample_request_symbols": [],
        "response_rows": None,
        "otm_puts_in_dte": getattr(stage2, "otm_puts_in_dte", 0),
        "otm_puts_in_delta_band": getattr(stage2, "otm_puts_in_delta_band", 0),
        "delta_abs_stats_otm_puts": None,
        "sample_otm_puts": [],
        "message": "Minimal trace (pipeline did not return full trace)",
    }
    if stage2 and getattr(stage2, "rejection_counts", None):
        minimal["rejection_counts"] = dict(stage2.rejection_counts)
    return minimal


def build_eligibility_layers(
    stage1: Optional["Stage1Result"],
    stage2: Optional["Stage2Result"],
    fetched_at_iso: Optional[str],
    market_open: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Build split eligibility layers from stage1/stage2.
    Returns (symbol_eligibility, contract_data, contract_eligibility).

    - Symbol eligibility: Stage-1 required snapshot fields only (PASS/FAIL).
    - Contract data.available: True when Stage-2 ran AND ORATS returned contracts (chain exists).
      NOT tied to selection outcome. UNAVAILABLE only when chain truly not fetched.
    - Contract eligibility: UNAVAILABLE (chain not fetched), FAIL (chain fetched, no candidates),
      or PASS (chain fetched, at least one candidate passed).
    """
    if stage1 is None:
        symbol_eligibility = {"status": "FAIL", "reasons": ["Stage 1 not run"]}
    else:
        passed = stage1.stock_verdict == StockVerdict.QUALIFIED
        symbol_eligibility = {
            "status": "PASS" if passed else "FAIL",
            "reasons": [] if passed else [stage1.stock_verdict_reason or "Stage 1 did not qualify"],
        }
        if stage1.missing_fields and not passed:
            symbol_eligibility["reasons"].append(f"Missing required fields: {', '.join(stage1.missing_fields)}")

    if stage2 is None:
        contract_data = {"available": False, "as_of": None, "source": "NONE"}
        contract_eligibility = {"status": "UNAVAILABLE", "reasons": ["Stage-2 did not execute or returned no contracts"]}
    else:
        # Phase 3.8: Single writer — contract_data from v2_stage2_response_builder when V2 trace present
        trace = getattr(stage2, "stage2_trace", None)
        if isinstance(trace, dict) and trace:
            from app.core.eval.v2_stage2_response_builder import build_canonical_payload, build_contract_data_from_canonical
            strategy_mode = (trace.get("mode") or "CSP").strip().upper()
            canonical = build_canonical_payload(strategy_mode, trace, fetched_at_iso)
            contract_data = build_contract_data_from_canonical(canonical)
        else:
            contracts_evaluated = getattr(stage2, "contracts_evaluated", 0) or 0
            fetch_error = getattr(stage2, "error", None)
            stage2_ran = stage2 is not None and not fetch_error and contracts_evaluated > 0
            option_type_counts = getattr(stage2, "option_type_counts", None) or {}
            delta_dist = getattr(stage2, "delta_distribution", None)
            top_rej = getattr(stage2, "top_rejection_reasons", None)
            required_fields_present = getattr(stage2, "required_fields_present", False)
            chain_source_used = getattr(stage2, "chain_source_used", None) or "DELAYED"
            contract_data = {
                "available": stage2_ran,
                "as_of": fetched_at_iso,
                "source": "NONE" if not stage2_ran else chain_source_used,
                "expiration_count": getattr(stage2, "expirations_evaluated", 0),
                "contract_count": contracts_evaluated,
                "required_fields_present": required_fields_present if stage2_ran else False,
                "total_puts_in_chain": getattr(stage2, "total_puts_in_chain", 0) or 0,
                "puts_with_required_fields": getattr(stage2, "puts_with_required_fields", 0) or 0,
                "option_type_counts": option_type_counts,
                "delta_distribution": delta_dist,
                "top_rejection_reasons": top_rej,
                "chain_missing_fields": getattr(stage2, "chain_missing_fields", []) or [],
                "rejection_counts": getattr(stage2, "rejection_counts", None) or {},
                "missing_required_fields_counts": getattr(stage2, "missing_required_fields_counts", None) or {},
                "sample_missing_required_contract": getattr(stage2, "sample_missing_required_contract", None),
                "strikes_options_telemetry": getattr(stage2, "strikes_options_telemetry", None),
                "stage2_trace": _ensure_stage2_trace(
                    _merge_stage2_trace_with_rejections(getattr(stage2, "stage2_trace", None), getattr(stage2, "rejection_counts", None)),
                    stage2,
                ),
                "otm_puts_in_dte": getattr(stage2, "otm_puts_in_dte", 0),
                "otm_puts_in_delta_band": getattr(stage2, "otm_puts_in_delta_band", 0),
                "spot_used": getattr(stage2, "spot_used", None),
            }

        candidates = getattr(stage2, "selected_candidates", []) or []
        stage2_ran = contract_data.get("available", False)

        # Step 3: contract_eligibility 3-way logic
        if not stage2_ran:
            contract_eligibility = {
                "status": "UNAVAILABLE",
                "reasons": ["Stage-2 did not execute or returned no contracts"],
            }
        elif not candidates:
            # Chain exists but no contract passed filters
            sel_reasons = getattr(stage2, "contract_selection_reasons", None) or []
            if sel_reasons:
                reasons = list(sel_reasons)
            else:
                reasons = [stage2.liquidity_reason or "No contracts passed option liquidity gates"]
            contract_eligibility = {"status": "FAIL", "reasons": reasons}
        else:
            # We have selected candidates
            passed = stage2.liquidity_ok
            reasons = []
            if not passed:
                sel_reasons = getattr(stage2, "contract_selection_reasons", None) or []
                if sel_reasons:
                    reasons = list(sel_reasons)
                else:
                    reasons = [stage2.liquidity_reason or "Options liquidity check failed"]
            contract_eligibility = {
                "status": "PASS" if passed else "FAIL",
                "reasons": reasons,
            }

    return symbol_eligibility, contract_data, contract_eligibility


# ============================================================================
# Full 2-Stage Evaluation
# ============================================================================

def evaluate_symbol_full(
    symbol: str,
    chain_provider: Optional[OratsChainProvider] = None,
    skip_stage2: bool = False,
    strategy_mode: str = "CSP",
    holdings: Optional[Dict[str, int]] = None,
) -> FullEvaluationResult:
    """
    Run full 2-stage evaluation for a symbol.
    Phase 4: Eligibility runs first; mode_decision (CSP | CC | NONE) from eligibility_engine.
    If NONE, Stage-2 is skipped. If CSP or CC, Stage-2 runs with that mode only.
    Args:
        symbol: Stock ticker
        chain_provider: Optional provider instance
        skip_stage2: If True, only run stage 1
        strategy_mode: Ignored when Phase 4 eligibility runs; used only as fallback if eligibility unavailable
        holdings: Symbol -> shares for CC (Phase 4). If None, treated as {} (CC ineligible).
    Returns:
        FullEvaluationResult with complete evaluation data and eligibility_trace
    """
    result = FullEvaluationResult(symbol=symbol, source="ORATS")
    now_iso = datetime.now(timezone.utc).isoformat()
    result.fetched_at = now_iso
    try:
        from app.market.market_hours import is_market_open
        market_open = is_market_open()
    except Exception:
        market_open = True

    # Stage 1
    stage1 = evaluate_stage1(symbol)
    result.stage1 = stage1
    result.stage_reached = EvaluationStage.STAGE1_ONLY
    
    # Copy stage 1 data to result
    result.price = stage1.price
    result.bid = stage1.bid
    result.ask = stage1.ask
    result.volume = stage1.volume
    result.avg_option_volume_20d = stage1.avg_option_volume_20d
    result.avg_stock_volume_20d = stage1.avg_stock_volume_20d
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

    # Phase 3.2.2: Underlying liquidity gates (always compute from stage1)
    underlying_gates = compute_underlying_liquidity_gates(stage1)
    
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
        result.liquidity_gates = {"underlying": underlying_gates, "option": compute_option_liquidity_gates(None)}
        se, cd, ce = build_eligibility_layers(stage1, None, now_iso, market_open)
        result.symbol_eligibility, result.contract_data, result.contract_eligibility = se, cd, ce
        return result

    # Skip stage 2 if requested
    if skip_stage2:
        result.options_available = True
        result.options_reason = "Stage 2 skipped"
        result.final_verdict = FinalVerdict.HOLD
        result.verdict = "HOLD"
        result.primary_reason = "Stock qualified, chain pending"
        result.score = stage1.stage1_score
        result.liquidity_gates = {"underlying": underlying_gates, "option": compute_option_liquidity_gates(None)}
        se, cd, ce = build_eligibility_layers(stage1, None, now_iso, market_open)
        result.symbol_eligibility, result.contract_data, result.contract_eligibility = se, cd, ce
        if not underlying_gates["passed"] and result.symbol_eligibility:
            result.symbol_eligibility = {"status": "FAIL", "reasons": [underlying_gates.get("reason") or "Underlying liquidity gates failed"]}
        return result

    # Phase 4: Eligibility gate (runs before Stage-2; decides mode CSP | CC | NONE)
    mode_decision = "CSP"
    try:
        from app.core.eligibility.eligibility_engine import run as run_eligibility
        mode_decision, eligibility_trace = run_eligibility(
            symbol, holdings=holdings or {}, current_price=stage1.price, lookback=255
        )
        result.eligibility_trace = eligibility_trace
    except Exception as e:
        logger.warning("[ELIGIBILITY] %s: %s; defaulting to CSP", symbol, e)
        result.eligibility_trace = {
            "symbol": symbol,
            "mode_decision": "CSP",
            "regime": "UNKNOWN",
            "rejection_reason_codes": ["ELIGIBILITY_ERROR"],
            "error": str(e),
        }

    if mode_decision == "NONE":
        result.options_available = False
        rej = (result.eligibility_trace or {}).get("rejection_reason_codes") or []
        result.options_reason = "; ".join(rej) if rej else "Eligibility: NONE"
        result.final_verdict = FinalVerdict.HOLD
        result.verdict = "HOLD"
        result.primary_reason = result.options_reason
        result.score = stage1.stage1_score
        result.liquidity_gates = {"underlying": underlying_gates, "option": compute_option_liquidity_gates(None)}
        se, cd, ce = build_eligibility_layers(stage1, None, now_iso, market_open)
        result.symbol_eligibility, result.contract_data, result.contract_eligibility = se, cd, ce
        if not underlying_gates["passed"] and result.symbol_eligibility:
            result.symbol_eligibility = {"status": "FAIL", "reasons": [underlying_gates.get("reason") or "Underlying liquidity gates failed"]}
        return result

    # Stage 2: eligibility is single source of truth. Ignore CLI/API strategy_mode for stage2.
    mode = mode_decision if mode_decision in ("CSP", "CC") else (strategy_mode or get_stage2_strategy_mode())
    stage2 = evaluate_stage2(symbol, stage1, chain_provider, strategy_mode=mode)
    
    # Log stage 2 result before enhancement
    logger.info(
        "[STAGE2] %s: initial_liquidity_ok=%s reason='%s' missing_fields=%s",
        symbol, stage2.liquidity_ok, stage2.liquidity_reason, stage2.chain_missing_fields
    )
    
    # V2-only: No post-selection enhancement. V2 engines are single source of truth (R3).
    result.stage2 = stage2
    result.stage_reached = EvaluationStage.STAGE2_CHAIN

    # Phase 3.2.2: Option liquidity gates (selected contract)
    option_contract = stage2.selected_contract.contract if stage2.selected_contract else None
    option_gates = compute_option_liquidity_gates(option_contract)
    result.liquidity_gates = {"underlying": underlying_gates, "option": option_gates}
    
    # Stage 1 required fields (price, bid, ask, volume, quote_date, iv_rank) are HARD required.
    # No waiver: if any were missing, Stage 1 would have BLOCKed and we would not reach Stage 2.

    # Add stage 2 gate (E: reason must match top rejection when FAIL)
    gate_reason = stage2.liquidity_reason
    if not stage2.liquidity_ok and getattr(stage2, "rejection_counts", None):
        rc = stage2.rejection_counts
        if rc:
            top_key = max(rc, key=rc.get)
            top_val = rc.get(top_key, 0)
            gate_reason = f"{stage2.liquidity_reason or 'No contract selected'} (top: {top_key}={top_val})"
    result.gates.append({
        "name": "Options Liquidity (Stage 2)",
        "status": "PASS" if stage2.liquidity_ok else "FAIL",
        "reason": gate_reason,
    })
    
    result.liquidity_ok = stage2.liquidity_ok
    result.liquidity_reason = stage2.liquidity_reason
    result.options_available = stage2.expirations_available > 0
    result.options_reason = f"{stage2.expirations_evaluated} expirations evaluated" if stage2.expirations_evaluated > 0 else "No expirations"
    
    # Do NOT re-add missing fields or downgrade data_completeness when OPRA passed (no secondary veto)
    if stage2.chain_missing_fields and not stage2.liquidity_ok:
        result.missing_fields.extend(stage2.chain_missing_fields)
        result.data_completeness = min(result.data_completeness, stage2.chain_completeness)
    
    # Phase 3.8: Single writer — candidate_trades from v2_stage2_response_builder only; strategy matches mode
    from app.core.eval.v2_stage2_response_builder import (
        build_canonical_payload,
        build_contract_data_from_canonical,
        build_candidate_trades_list,
    )
    trace = getattr(stage2, "stage2_trace", None) or {}
    strategy_mode = (trace.get("mode") or mode or "CSP").strip().upper()
    selected_trade_dict = trace.get("selected_trade") if isinstance(trace, dict) else None
    result.candidate_trades = build_candidate_trades_list(
        strategy_mode,
        selected_trade_dict,
        selected_contract_legacy=stage2.selected_contract,
    )
    
    # Determine final verdict
    # Check for ELIGIBLE: either selected_contract exists OR liquidity was confirmed via enhancement
    is_enhanced = "(enhanced)" in (stage2.liquidity_reason or "")
    
    if stage2.liquidity_ok and stage2.selected_contract:
        # Standard path: contract selected from chain provider
        result.final_verdict = FinalVerdict.ELIGIBLE
        result.verdict = "ELIGIBLE"
        result.primary_reason = f"Chain evaluated, contract selected: {stage2.selected_contract.selection_reason}"
    elif stage2.liquidity_ok and is_enhanced:
        # OPRA path: liquidity from /datav2/strikes/options; stock bid/ask/volume are not waived
        result.final_verdict = FinalVerdict.ELIGIBLE
        result.verdict = "ELIGIBLE"
        result.primary_reason = f"Options liquidity confirmed (OPRA): {stage2.liquidity_reason}"
        logger.info("[VERDICT] %s: ELIGIBLE via OPRA liquidity", symbol)
    elif stage2.error:
        result.final_verdict = FinalVerdict.UNKNOWN
        result.verdict = "UNKNOWN"
        result.primary_reason = f"Chain evaluation error: {stage2.error}"
        result.error = stage2.error
    elif stage2.chain_missing_fields:
        # Option-chain fields only; do not imply stock bid/ask missing
        result.final_verdict = FinalVerdict.HOLD
        result.verdict = "HOLD"
        result.primary_reason = f"OPTION_CHAIN_MISSING_FIELDS: {', '.join(stage2.chain_missing_fields)}"
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

    se, cd, ce = build_eligibility_layers(stage1, result.stage2, now_iso, market_open)
    result.symbol_eligibility, result.contract_data, result.contract_eligibility = se, cd, ce
    # Phase 3.2.2: Enforce liquidity gates in eligibility
    if not underlying_gates["passed"] and result.symbol_eligibility:
        result.symbol_eligibility = {"status": "FAIL", "reasons": [underlying_gates.get("reason") or "Underlying liquidity gates failed"]}
    if not option_gates["passed"] and result.contract_eligibility and result.contract_eligibility.get("status") != "UNAVAILABLE":
        result.contract_eligibility = {"status": "FAIL", "reasons": [option_gates.get("reason") or "Option liquidity gates failed"]}
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

    Stage-2 always uses DELAYED chain for reliable per-contract option_type/delta/OI.
    """
    provider = chain_provider or get_chain_provider(chain_source=get_stage2_chain_source())
    results: Dict[str, FullEvaluationResult] = {}
    
    logger.info("[STAGED_EVAL] Starting 2-stage evaluation for %d symbols", len(symbols))
    start_time = time.time()
    
    # Phase 8D: Per-run ORATS cache — pre-fetch equity + ivrank for all symbols so stage1 uses cache
    try:
        from app.core.data.orats_client import reset_run_cache, fetch_full_equity_snapshots
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

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        from app.market.market_hours import is_market_open
        _market_open = is_market_open()
    except Exception:
        _market_open = True

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
            result.avg_option_volume_20d = stage1.avg_option_volume_20d
            result.avg_stock_volume_20d = stage1.avg_stock_volume_20d
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
            se, cd, ce = build_eligibility_layers(stage1, None, now_iso, _market_open)
            result.symbol_eligibility, result.contract_data, result.contract_eligibility = se, cd, ce
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
                se, cd, ce = build_eligibility_layers(stage1, None, now_iso, _market_open)
                result.symbol_eligibility, result.contract_data, result.contract_eligibility = se, cd, ce
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
