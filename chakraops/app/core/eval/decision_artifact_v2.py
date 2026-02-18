# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.6: Canonical DecisionArtifactV2 schema — ONE pipeline, ONE artifact, ONE store."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

# Band mapping: centralized logic. NEVER null — D for lowest.
try:
    from app.core.scoring.config import TIER_A_MIN, TIER_B_MIN, TIER_C_MIN
except Exception:
    TIER_A_MIN, TIER_B_MIN, TIER_C_MIN = 80, 60, 40


def assign_band(score: Optional[int | float]) -> str:
    """Centralized band assignment. NEVER null — returns A|B|C|D."""
    if score is None:
        return "D"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "D"
    if s >= TIER_A_MIN:
        return "A"
    if s >= TIER_B_MIN:
        return "B"
    if s >= TIER_C_MIN:
        return "C"
    return "D"  # Below C — always D, never null


def assign_band_reason(score: Optional[int | float]) -> str:
    """Band reason from score thresholds only. NEVER mentions verdict (verdict is separate)."""
    b = assign_band(score)
    if score is None:
        return f"Band {b} because score is None/invalid (default)"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return f"Band {b} because score is invalid (default)"
    if b == "A":
        return f"Band {b} because score >= {TIER_A_MIN}"
    if b == "B":
        return f"Band {b} because score >= {TIER_B_MIN} and < {TIER_A_MIN}"
    if b == "C":
        return f"Band {b} because score >= {TIER_C_MIN} and < {TIER_B_MIN}"
    return f"Band {b} because score < {TIER_C_MIN}"


def _band_rank_value(band: str) -> int:
    """Numeric value for band ordering (A > B > C > D). Phase 8.0."""
    return {"A": 4, "B": 3, "C": 2, "D": 1}.get((band or "D").upper(), 1)


def compute_rank_score(
    band: str,
    score: Optional[float],
    premium_yield_pct: Optional[float],
    capital_required: Optional[float],
    market_cap: Optional[float],
) -> float:
    """
    Phase 8.0: Sortable rank_score.
    Primary: band (A>B>C>D), Secondary: score desc, Tertiary: premium_yield desc,
    Quaternary: capital_required asc, Tie-breaker: market_cap desc.
    """
    band_val = _band_rank_value(band) * 100_000
    score_val = (score if score is not None else 0) * 100
    yield_val = (premium_yield_pct if premium_yield_pct is not None else 0) * 10
    cap_val = -(capital_required or 999_999) / 100  # lower capital = higher rank
    mcap_val = (market_cap or 0) / 1e9
    return band_val + score_val + yield_val + cap_val + mcap_val


@dataclass
class SymbolEvalSummary:
    """One row per universe symbol. All fields explicit (no optional blanks)."""
    symbol: str
    verdict: str  # ELIGIBLE|HOLD|BLOCKED|NOT_EVALUATED
    final_verdict: str
    score: Optional[int | float]
    band: str  # A|B|C|D — never null
    primary_reason: Optional[str]
    stage_status: str  # RUN|NOT_RUN
    stage1_status: str  # PASS|FAIL|NOT_RUN
    stage2_status: str  # PASS|FAIL|NOT_RUN
    provider_status: Optional[str]  # OK|WARN|ERROR
    data_freshness: Optional[str]  # ISO
    evaluated_at: Optional[str]   # ISO
    strategy: Optional[str]  # CSP|CC|STOCK
    price: Optional[float]
    expiration: Optional[str]  # ISO or YYYY-MM-DD
    has_candidates: bool
    candidate_count: int
    # Phase 7.7 / 10.1: Trust + score clarity
    score_breakdown: Optional[Dict[str, Any]] = None  # stage1_score, stage2_score, raw_score, final_score, score_caps, regime_score
    raw_score: Optional[int | float] = None  # composite before any cap (0-100)
    pre_cap_score: Optional[int | float] = None  # same as raw_score; alias for display
    final_score: Optional[int | float] = None  # after caps; band is derived from this only
    score_caps: Optional[Dict[str, Any]] = None  # { regime_cap, applied_caps: [{type, cap_value, before, after, reason}] }
    band_reason: Optional[str] = None  # "Band A because score >= TIER_A_MIN"
    max_loss: Optional[float] = None  # capital required for selected candidate
    underlying_price: Optional[float] = None  # spot at evaluation
    # Phase 8.0: Ranking fields
    capital_required: Optional[float] = None  # underlying_price * 100
    expected_credit: Optional[float] = None  # from selected candidate if eligible
    premium_yield_pct: Optional[float] = None  # expected_credit / capital_required
    market_cap: Optional[float] = None  # if available
    rank_score: Optional[float] = None  # sortable numeric score

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateRow:
    """Single candidate (trade proposal) for a symbol."""
    symbol: str
    strategy: str
    expiry: Optional[str]
    strike: Optional[float]
    delta: Optional[float]
    credit_estimate: Optional[float]
    max_loss: Optional[float]
    why_this_trade: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GateEvaluation:
    """Gate pass/fail for Explain This Decision."""
    name: str
    status: str  # PASS|FAIL|SKIP
    reason: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EarningsInfo:
    """Earnings info for a symbol."""
    earnings_days: Optional[int]
    earnings_block: Optional[bool]
    note: Optional[str]  # e.g. "Not evaluated"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolDiagnosticsDetails:
    """Phase 7.7: Full diagnostics per symbol for Symbol page. Persisted in v2 artifact."""
    # Technicals (from eligibility_trace / computed)
    technicals: Dict[str, Any]  # rsi, atr, atr_pct, support_level, resistance_level
    # Exit plan (T1, T2, T3, stop from build_exit_plan)
    exit_plan: Dict[str, Any]  # t1, t2, t3, stop
    # Risk flags
    risk_flags: Dict[str, Any]  # earnings_days, earnings_block, stock_liq, option_liq, data_status, missing_required
    # Phase 7.3 explanation
    explanation: Dict[str, Any]  # stock_regime_reason, support_condition, liquidity_condition, iv_condition
    # Stock snapshot (price, bid, ask, volume, etc.)
    stock: Dict[str, Any]
    # Symbol eligibility detail
    symbol_eligibility: Dict[str, Any]  # status, required_data_missing, required_data_stale, reasons
    # Liquidity detail
    liquidity: Dict[str, Any]  # stock_liquidity_ok, option_liquidity_ok, reason
    # Score breakdown and band
    score_breakdown: Optional[Dict[str, Any]] = None
    rank_reasons: Optional[Dict[str, Any]] = None
    suggested_capital_pct: Optional[float] = None
    regime: Optional[str] = None
    # Provider/options metadata
    options: Dict[str, Any] = field(default_factory=dict)  # expirations_count, contracts_count, underlying_price

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionArtifactV2:
    """Canonical evaluation output. ONE schema used everywhere."""
    metadata: Dict[str, Any]  # artifact_version, mode, pipeline_timestamp, etc.
    symbols: List[SymbolEvalSummary]  # ONE ROW PER UNIVERSE SYMBOL
    selected_candidates: List[CandidateRow]  # for Dashboard A/B lists
    candidates_by_symbol: Dict[str, List[CandidateRow]] = field(default_factory=dict)
    gates_by_symbol: Dict[str, List[GateEvaluation]] = field(default_factory=dict)
    earnings_by_symbol: Dict[str, EarningsInfo] = field(default_factory=dict)
    diagnostics_by_symbol: Dict[str, SymbolDiagnosticsDetails] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "metadata": self.metadata,
            "symbols": [s.to_dict() for s in self.symbols],
            "selected_candidates": [c.to_dict() for c in self.selected_candidates],
            "candidates_by_symbol": {
                k: [c.to_dict() for c in v]
                for k, v in self.candidates_by_symbol.items()
            },
            "gates_by_symbol": {
                k: [g.to_dict() for g in v]
                for k, v in self.gates_by_symbol.items()
            },
            "earnings_by_symbol": {
                k: v.to_dict() for k, v in self.earnings_by_symbol.items()
            },
            "diagnostics_by_symbol": {
                k: v.to_dict() for k, v in self.diagnostics_by_symbol.items()
            },
            "warnings": self.warnings,
        }
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionArtifactV2":
        meta = data.get("metadata") or {}
        sym_fields = {f.name for f in SymbolEvalSummary.__dataclass_fields__.values()}
        symbols = []
        for s in data.get("symbols") or []:
            row = s if isinstance(s, dict) else asdict(s)
            d = {k: v for k, v in row.items() if k in sym_fields}
            # Band never null: derive from final_score only (Phase 10.1)
            if d.get("band") not in ("A", "B", "C", "D"):
                d["band"] = assign_band(d.get("final_score") or d.get("score"))
            symbols.append(SymbolEvalSummary(**d))
        cand_fields = {f.name for f in CandidateRow.__dataclass_fields__.values()}
        selected = [
            CandidateRow(**{k: v for k, v in (c if isinstance(c, dict) else asdict(c)).items() if k in cand_fields})
            for c in data.get("selected_candidates") or []
        ]
        cb = data.get("candidates_by_symbol") or {}
        candidates_by_symbol = {
            k: [CandidateRow(**c) if isinstance(c, dict) else c for c in v]
            for k, v in cb.items()
        }
        gb = data.get("gates_by_symbol") or {}
        gates_by_symbol = {
            k: [GateEvaluation(**g) if isinstance(g, dict) else g for g in v]
            for k, v in gb.items()
        }
        eb = data.get("earnings_by_symbol") or {}
        earnings_by_symbol = {
            k: EarningsInfo(**v) if isinstance(v, dict) else v
            for k, v in eb.items()
        }
        db = data.get("diagnostics_by_symbol") or {}
        diag_fields = {f.name for f in SymbolDiagnosticsDetails.__dataclass_fields__.values()}
        _empty: Dict[str, Any] = {}
        diagnostics_by_symbol = {}
        for k, v in db.items():
            if isinstance(v, dict):
                d = {x: (v[x] if x in v else (_empty if x in ("technicals", "exit_plan", "risk_flags", "explanation", "stock", "symbol_eligibility", "liquidity", "options") else None))
                     for x in diag_fields}
                diagnostics_by_symbol[k] = SymbolDiagnosticsDetails(**d)
            elif isinstance(v, SymbolDiagnosticsDetails):
                diagnostics_by_symbol[k] = v
        return cls(
            metadata=meta,
            symbols=symbols,
            selected_candidates=selected,
            candidates_by_symbol=candidates_by_symbol,
            gates_by_symbol=gates_by_symbol,
            earnings_by_symbol=earnings_by_symbol,
            diagnostics_by_symbol=diagnostics_by_symbol,
            warnings=data.get("warnings") or [],
        )
