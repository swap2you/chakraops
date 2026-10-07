# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8: Strategy Explainability Layer.

Every verdict has a human-readable StrategyRationale (summary, bullets,
failed_checks, data_warnings). Built alongside score and persisted in evaluation run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class StrategyRationale:
    """Human-readable explanation for a symbol's verdict."""
    summary: str
    bullets: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    data_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "bullets": list(self.bullets),
            "failed_checks": list(self.failed_checks),
            "data_warnings": list(self.data_warnings),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StrategyRationale":
        return cls(
            summary=d.get("summary", ""),
            bullets=list(d.get("bullets", [])),
            failed_checks=list(d.get("failed_checks", [])),
            data_warnings=list(d.get("data_warnings", [])),
        )


def build_rationale_from_staged(
    symbol: str,
    verdict: str,
    primary_reason: str,
    stage1: Any,
    stage2: Any,
    market_regime: str,
    score: int,
    data_completeness: float,
    missing_fields: List[str],
    position_open: bool = False,
    position_reason: Optional[str] = None,
) -> StrategyRationale:
    """
    Build StrategyRationale from staged evaluation result.
    Used by staged_evaluator when assembling FullEvaluationResult.
    """
    bullets: List[str] = []
    failed_checks: List[str] = []
    data_warnings: List[str] = []

    # Market regime
    if market_regime == "RISK_OFF":
        failed_checks.append("Blocked by market regime: RISK_OFF")
        bullets.append("Market regime: RISK_OFF (scores capped, verdict HOLD)")
    elif market_regime == "NEUTRAL":
        bullets.append("Market regime: NEUTRAL (score capped at 65)")
    else:
        bullets.append(f"Market regime: {market_regime}")

    # Stage 1 / IVR band (Phase 3.2.3: bands only, no trend logic)
    if stage1:
        if getattr(stage1, "regime", None):
            bullets.append(f"IV regime: {stage1.regime}")
        iv_rank = getattr(stage1, "iv_rank", None)
        ivr_band = getattr(stage1, "ivr_band", None)
        if iv_rank is not None:
            if ivr_band == "LOW":
                bullets.append(f"IV Rank low ({iv_rank:.0f}) — premium penalized")
            elif ivr_band == "MID":
                bullets.append(f"IV Rank neutral ({iv_rank:.0f})")
            elif ivr_band == "HIGH":
                bullets.append(f"IV Rank high ({iv_rank:.0f}) — favorable premium")
                bullets.append("High IV Rank: favorable premium but elevated tail risk (larger moves).")
            else:
                bullets.append(f"IV Rank: {iv_rank:.0f}")
        sv = getattr(stage1, "stock_verdict", None)
        sv_val = getattr(sv, "value", str(sv)) if sv else ""
        if sv and sv_val != "QUALIFIED":
            failed_checks.append(getattr(stage1, "stock_verdict_reason", "Stage 1 failed"))

    # Data completeness
    if data_completeness < 1.0 and missing_fields:
        data_warnings.append(f"Liquidity incomplete (missing {', '.join(missing_fields[:5])})")
        if "bid" in missing_fields or "ask" in missing_fields:
            data_warnings.append("Missing bid/ask")
    if data_completeness < 0.75:
        failed_checks.append("DATA_INCOMPLETE: insufficient data for eligibility")

    # Phase 9: Position awareness
    if position_open and position_reason:
        failed_checks.append(f"Blocked by position: {position_reason}")

    # Stage 2 / liquidity
    if stage2:
        if getattr(stage2, "liquidity_ok", False):
            bullets.append(f"Liquidity: {getattr(stage2, 'liquidity_reason', 'OK')}")
        else:
            reason = getattr(stage2, "liquidity_reason", "Insufficient liquidity")
            failed_checks.append(reason)
        if getattr(stage2, "chain_missing_fields", None):
            data_warnings.append(f"Chain missing: {', '.join(stage2.chain_missing_fields[:3])}")

    # Summary
    if failed_checks:
        summary = primary_reason or failed_checks[0]
    else:
        summary = primary_reason or f"Verdict: {verdict} (score {score})"
    if not summary.strip():
        summary = f"{verdict} — score {score}"

    return StrategyRationale(
        summary=summary,
        bullets=bullets,
        failed_checks=failed_checks,
        data_warnings=data_warnings,
    )
