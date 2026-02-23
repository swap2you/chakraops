# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R22.8: Offline proof harness — build UniverseEvaluationResult from fixture JSON (no live ORATS)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.core.eval.universe_evaluator import (
    CandidateTrade,
    SymbolEvaluationResult,
    UniverseEvaluationResult,
)


def load_fixture(fixture_path: Path) -> Dict[str, Any]:
    """Load R22.8 offline proof fixture JSON."""
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_universe_result_from_fixture(fixture_path: Path) -> UniverseEvaluationResult:
    """
    Build UniverseEvaluationResult from fixture. Used by offline_eval_proof script and tests.
    Produces code-only friendly fields (reason_code, rank_reason_codes) so persisted artifact is hygiene-compliant.
    """
    data = load_fixture(fixture_path)
    symbols: List[str] = data.get("symbols") or []
    quotes: Dict[str, Dict[str, Any]] = data.get("quotes") or {}
    overrides: Dict[str, Dict[str, Any]] = data.get("eval_overrides") or {}

    symbol_results: List[SymbolEvaluationResult] = []
    for sym in symbols:
        sym_upper = (sym or "").strip().upper()
        if not sym_upper:
            continue
        q = quotes.get(sym_upper) or {}
        ov = overrides.get(sym_upper) or {}
        verdict = (ov.get("verdict") or "HOLD").upper()
        if verdict not in ("ELIGIBLE", "HOLD", "BLOCKED", "NOT_EVALUATED"):
            verdict = "HOLD"
        score = ov.get("score")
        if score is None:
            score = 50
        primary_reason = ov.get("primary_reason") or "REGIME_NEUTRAL_CAP"
        stage_reached = ov.get("stage_reached") or "STAGE1_ONLY"

        # Code-only: applied_caps use reason_code; rank_reasons use rank_reason_codes
        applied_caps = [
            {
                "type": "REGIME_CAP",
                "cap_value": 65,
                "before": min(score, 100),
                "after": min(score, 65),
                "reason_code": "REGIME_NEUTRAL",
            }
        ]
        if verdict == "ELIGIBLE":
            applied_caps = []
        score_breakdown = {
            "stage1_score": score,
            "raw_score": score,
            "final_score": score,
            "score_caps": {"applied_caps": applied_caps},
        }
        rank_reasons = {"rank_reason_codes": ["REGIME_NEUTRAL", "DATA_COMPLETE"]}

        symbol_eligibility = {"status": "PASS", "reasons": []}

        gates = [{"name": "STOCK_QUALITY_STAGE1", "status": "PASS", "reason": "OK"}]
        candidate_trades_list: List[CandidateTrade] = []
        selected_contract = None
        selected_expiration = None
        if verdict == "ELIGIBLE" and stage_reached == "STAGE2_CHAIN":
            candidate_trades_list = [
                CandidateTrade(
                    strategy="CSP",
                    expiry="2026-03-20",
                    strike=140.0,
                    delta=-0.25,
                    credit_estimate=2.50,
                    max_loss=None,
                    why_this_trade="",
                )
            ]
            selected_contract = {
                "strategy": "CSP",
                "expiration": "2026-03-20",
                "strike": 140.0,
                "delta": -0.25,
                "credit_estimate": 2.50,
                "max_loss": None,
                "contract": {"option_symbol": "NVDA260320P00140000", "strike": 140.0, "delta": -0.25},
            }
            selected_expiration = "2026-03-20"

        sr = SymbolEvaluationResult(
            symbol=sym_upper,
            source="FIXTURE",
            price=q.get("price"),
            bid=q.get("bid"),
            ask=q.get("ask"),
            volume=q.get("volume"),
            verdict=verdict,
            primary_reason=primary_reason,
            score=score,
            regime="NEUTRAL",
            risk="MODERATE",
            liquidity_ok=True,
            options_available=(verdict == "ELIGIBLE"),
            options_reason="" if verdict == "ELIGIBLE" else "NOT_IN_TOP_K",
            gates=gates,
            blockers=[],
            candidate_trades=candidate_trades_list,
            fetched_at="2026-02-17T12:00:00Z",
            quote_date=q.get("quote_date") or "2026-02-17",
            data_completeness=1.0,
            missing_fields=[],
            data_quality_details={},
            stage_reached=stage_reached,
            selected_contract=selected_contract,
            selected_expiration=selected_expiration,
            score_breakdown=score_breakdown,
            rank_reasons=rank_reasons,
            symbol_eligibility=symbol_eligibility,
            contract_data={"available": True, "as_of": "2026-02-17T12:00:00Z"},
            contract_eligibility={"status": "PASS", "reasons": []},
        )
        symbol_results.append(sr)

    eligible_count = sum(1 for s in symbol_results if s.verdict == "ELIGIBLE")
    return UniverseEvaluationResult(
        evaluation_state="COMPLETED",
        evaluation_state_reason=f"Offline fixture: {len(symbol_results)} symbols",
        total=len(symbols),
        evaluated=len(symbol_results),
        eligible=eligible_count,
        symbols=symbol_results,
        alerts=[],
        errors=[],
        engine="staged",
    )
