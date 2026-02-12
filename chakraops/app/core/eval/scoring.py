# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 3: Explainable scoring and capital-aware ranking.

- Score breakdown: data_quality_score, regime_score, options_liquidity_score,
  strategy_fit_score, capital_efficiency_score (with weights from config/scoring.yaml).
- Capital efficiency: csp_notional = strike * 100; notional_pct = csp_notional / account_equity;
  penalize when notional_pct exceeds thresholds (config-driven). No price-level penalties.
- Rank reasons: top 3 positive reasons + top 1 penalty for UI.
- Band assignment uses breakdown + gates; band_reason explains why (so Band C is not unexplained).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Defaults (conservative) when config is missing
_DEFAULT_WEIGHTS = {
    "data_quality": 0.25,
    "regime": 0.20,
    "options_liquidity": 0.20,
    "strategy_fit": 0.20,
    "capital_efficiency": 0.15,
}
_DEFAULT_NOTIONAL_THRESHOLDS = {"warn_above": 0.05, "heavy_penalty_above": 0.10, "cap_above": 0.20}
_DEFAULT_NOTIONAL_PENALTIES = {"warn": 5, "heavy": 15, "cap": 30}
_DEFAULT_BAND_A_MIN = 78
_DEFAULT_BAND_B_MIN = 60


def _repo_root() -> Path:
    """ChakraOps repo root (chakraops/)."""
    return Path(__file__).resolve().parents[3]


def _load_scoring_config() -> dict:
    """Load config/scoring.yaml. Returns empty dict if not found."""
    path = _repo_root() / "config" / "scoring.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to load scoring config: %s", e)
        return {}


def get_account_equity() -> Optional[float]:
    """Account equity for notional_pct.

    Priority:
      1. Env ACCOUNT_EQUITY (override for testing/CI)
      2. Default account total_capital (Phase 1 accounts system)
      3. config/scoring.yaml account_equity (legacy fallback)
    """
    # 1. Env override
    env_val = os.getenv("ACCOUNT_EQUITY")
    if env_val is not None:
        try:
            return float(env_val)
        except ValueError:
            pass
    # 2. Default account (Phase 1)
    try:
        from app.core.accounts.service import get_account_equity_from_default
        acct_equity = get_account_equity_from_default()
        if acct_equity is not None:
            return acct_equity
    except ImportError:
        pass
    # 3. Legacy config fallback
    cfg = _load_scoring_config()
    val = cfg.get("account_equity")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def get_scoring_weights() -> Dict[str, float]:
    """Weights for components (must sum to 1.0)."""
    cfg = _load_scoring_config()
    w = cfg.get("weights") or {}
    return {
        "data_quality": float(w.get("data_quality", _DEFAULT_WEIGHTS["data_quality"])),
        "regime": float(w.get("regime", _DEFAULT_WEIGHTS["regime"])),
        "options_liquidity": float(w.get("options_liquidity", _DEFAULT_WEIGHTS["options_liquidity"])),
        "strategy_fit": float(w.get("strategy_fit", _DEFAULT_WEIGHTS["strategy_fit"])),
        "capital_efficiency": float(w.get("capital_efficiency", _DEFAULT_WEIGHTS["capital_efficiency"])),
    }


def get_notional_thresholds() -> Dict[str, float]:
    """Notional % thresholds (warn_above, heavy_penalty_above, cap_above)."""
    cfg = _load_scoring_config()
    t = (cfg.get("notional_pct_thresholds") or {})
    return {
        "warn_above": float(t.get("warn_above", _DEFAULT_NOTIONAL_THRESHOLDS["warn_above"])),
        "heavy_penalty_above": float(t.get("heavy_penalty_above", _DEFAULT_NOTIONAL_THRESHOLDS["heavy_penalty_above"])),
        "cap_above": float(t.get("cap_above", _DEFAULT_NOTIONAL_THRESHOLDS["cap_above"])),
    }


def get_notional_penalties() -> Dict[str, int]:
    """Penalty points per notional band (warn, heavy, cap)."""
    cfg = _load_scoring_config()
    p = (cfg.get("notional_penalties") or {})
    return {
        "warn": int(p.get("warn", _DEFAULT_NOTIONAL_PENALTIES["warn"])),
        "heavy": int(p.get("heavy", _DEFAULT_NOTIONAL_PENALTIES["heavy"])),
        "cap": int(p.get("cap", _DEFAULT_NOTIONAL_PENALTIES["cap"])),
    }


def get_band_limits() -> Tuple[int, int]:
    """(band_a_min_score, band_b_min_score)."""
    cfg = _load_scoring_config()
    a = int(cfg.get("band_a_min_score", _DEFAULT_BAND_A_MIN))
    b = int(cfg.get("band_b_min_score", _DEFAULT_BAND_B_MIN))
    return a, b


# ---------------------------------------------------------------------------
# Component scores (0-100 each)
# ---------------------------------------------------------------------------

def data_quality_score(data_completeness: float) -> int:
    """0-100 from data completeness (0.0-1.0)."""
    return max(0, min(100, int(round(data_completeness * 100))))


def regime_score(regime: Optional[str]) -> int:
    """
    0-100 from market regime (Phase 3.2.3: IVR band–driven).
    LOW_VOL=40 (penalize), NEUTRAL=65, HIGH_VOL=85 (positive).
    Legacy: RISK_ON=100, RISK_OFF=50, UNKNOWN=50.
    """
    r = (regime or "").strip().upper()
    if r == "LOW_VOL":
        return 40   # Penalize: low IV rank
    if r == "NEUTRAL":
        return 65
    if r == "HIGH_VOL":
        return 85   # Positive: high IV (tail risk noted in rationale)
    if r == "RISK_ON":
        return 100
    if r == "RISK_OFF":
        return 50
    return 50


def options_liquidity_score(liquidity_ok: bool, liquidity_grade: Optional[str]) -> int:
    """0-100 from liquidity pass and grade. A=100, B=80, C=60, else 40; fail=20."""
    if not liquidity_ok:
        return 20
    g = (liquidity_grade or "").strip().upper()
    if g == "A":
        return 100
    if g == "B":
        return 80
    if g == "C":
        return 60
    return 40


def strategy_fit_score(verdict: str, position_open: bool) -> int:
    """0-100: ELIGIBLE and no position = 100; ELIGIBLE with position = 70; HOLD = 50; BLOCKED = 20."""
    v = (verdict or "").strip().upper()
    if v == "ELIGIBLE":
        return 70 if position_open else 100
    if v == "HOLD":
        return 50
    if v in ("BLOCKED", "UNKNOWN"):
        return 20
    return 50


def capital_efficiency_score(
    csp_notional: Optional[float],
    account_equity: Optional[float],
    price: Optional[float],
) -> Tuple[int, List[str], Optional[str]]:
    """
    Compute 0-100 capital efficiency component and penalty reasons.

    - csp_notional = selected_put_strike * 100 (or None if no put).
    - notional_pct = csp_notional / account_equity when both set.
    - Penalize only by notional_pct thresholds (config-driven). No price-level penalties.
    Returns (score, list of penalty reason strings, top_penalty for rank_reasons).
    """
    score = 100
    penalties: List[str] = []
    top_penalty: Optional[str] = None

    if account_equity is None or account_equity <= 0:
        return (100, penalties, top_penalty)

    if csp_notional is None or csp_notional <= 0:
        return (100, penalties, top_penalty)

    notional_pct = csp_notional / account_equity
    thresh = get_notional_thresholds()
    pen = get_notional_penalties()

    if notional_pct >= thresh["cap_above"]:
        score -= pen["cap"]
        penalties.append(f"Notional {notional_pct:.1%} of account (cap)")
        if top_penalty is None:
            top_penalty = f"CSP notional {notional_pct:.1%} of account"
    elif notional_pct >= thresh["heavy_penalty_above"]:
        score -= pen["heavy"]
        penalties.append(f"Notional {notional_pct:.1%} of account (heavy)")
        if top_penalty is None:
            top_penalty = f"CSP notional {notional_pct:.1%} of account"
    elif notional_pct >= thresh["warn_above"]:
        score -= pen["warn"]
        penalties.append(f"Notional {notional_pct:.1%} of account (warn)")
        if top_penalty is None:
            top_penalty = f"CSP notional {notional_pct:.1%} of account"

    return (max(0, min(100, score)), penalties, top_penalty)


# ---------------------------------------------------------------------------
# Breakdown and composite score
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    """Per-symbol score breakdown for UI and banding."""
    data_quality_score: int
    regime_score: int
    options_liquidity_score: int
    strategy_fit_score: int
    capital_efficiency_score: int
    composite_score: int  # weighted sum, 0-100
    csp_notional: Optional[float] = None
    notional_pct: Optional[float] = None
    capital_penalties: List[str] = field(default_factory=list)
    top_penalty: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_quality_score": self.data_quality_score,
            "regime_score": self.regime_score,
            "options_liquidity_score": self.options_liquidity_score,
            "strategy_fit_score": self.strategy_fit_score,
            "capital_efficiency_score": self.capital_efficiency_score,
            "composite_score": self.composite_score,
            "csp_notional": self.csp_notional,
            "notional_pct": self.notional_pct,
            "capital_penalties": self.capital_penalties,
            "top_penalty": self.top_penalty,
        }


def compute_score_breakdown(
    *,
    data_completeness: float,
    regime: Optional[str],
    liquidity_ok: bool,
    liquidity_grade: Optional[str],
    verdict: str,
    position_open: bool,
    price: Optional[float],
    selected_put_strike: Optional[float],
    # Optional override for final composite (e.g. after regime cap applied elsewhere)
    base_composite_override: Optional[int] = None,
) -> Tuple[ScoreBreakdown, int]:
    """
    Compute full breakdown and final score (0-100).

    If base_composite_override is set, it is used as the composite after weighting;
    otherwise composite = weighted sum of components. Final score is then
    min(composite, regime_cap) where regime cap is applied in caller if needed.
    Returns (ScoreBreakdown, final_score).
    """
    account_equity = get_account_equity()
    csp_notional = (selected_put_strike * 100) if selected_put_strike is not None else None
    notional_pct = None
    if csp_notional is not None and account_equity is not None and account_equity > 0:
        notional_pct = csp_notional / account_equity

    ce_score, capital_penalties, top_penalty = capital_efficiency_score(
        csp_notional, account_equity, price
    )

    dq = data_quality_score(data_completeness)
    rg = regime_score(regime)
    liq = options_liquidity_score(liquidity_ok, liquidity_grade)
    fit = strategy_fit_score(verdict, position_open)

    weights = get_scoring_weights()
    composite = int(round(
        dq * weights["data_quality"] +
        rg * weights["regime"] +
        liq * weights["options_liquidity"] +
        fit * weights["strategy_fit"] +
        ce_score * weights["capital_efficiency"]
    ))
    composite = max(0, min(100, composite))

    if base_composite_override is not None:
        composite = max(0, min(100, base_composite_override))

    breakdown = ScoreBreakdown(
        data_quality_score=dq,
        regime_score=rg,
        options_liquidity_score=liq,
        strategy_fit_score=fit,
        capital_efficiency_score=ce_score,
        composite_score=composite,
        csp_notional=csp_notional,
        notional_pct=notional_pct,
        capital_penalties=capital_penalties,
        top_penalty=top_penalty,
    )
    return breakdown, composite


def build_rank_reasons(
    breakdown: ScoreBreakdown,
    regime: Optional[str],
    data_completeness: float,
    liquidity_ok: bool,
    verdict: str,
) -> Dict[str, Any]:
    """
    Top 3 reasons (positive) + top 1 penalty for UI "Rank reasons" text.
    Returns { "reasons": ["...", "...", "..."], "penalty": "..." or null }.
    """
    reasons: List[str] = []
    if regime == "RISK_ON":
        reasons.append("Regime RISK_ON")
    elif regime == "NEUTRAL":
        reasons.append("Regime NEUTRAL")
    elif regime == "HIGH_VOL":
        reasons.append("IV Rank HIGH (favorable premium)")
    if data_completeness >= 0.9:
        reasons.append("High data completeness")
    elif data_completeness >= 0.75:
        reasons.append("Acceptable data completeness")
    if liquidity_ok:
        reasons.append("Options liquidity passed")
    if verdict == "ELIGIBLE":
        reasons.append("Eligible for trade")
    if breakdown.capital_efficiency_score >= 90 and not breakdown.capital_penalties:
        reasons.append("Capital efficient")
    elif breakdown.notional_pct is not None and breakdown.notional_pct < 0.05:
        reasons.append("Low notional % of account")

    # Keep at most 3
    reasons = reasons[:3]
    penalty = breakdown.top_penalty
    return {"reasons": reasons, "penalty": penalty}
