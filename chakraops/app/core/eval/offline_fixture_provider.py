# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R22.8/R25.1: Offline proof harness — build UniverseEvaluationResult from fixture JSON (no live ORATS).

R25.1: Deterministic fixtures for OHLC bars, option chain candidates (stable contract_key),
quotes (spot + option bid/ask/last + quote_ts), and account settings for sizing. No network calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.core.eval.universe_evaluator import (
    CandidateTrade,
    SymbolEvaluationResult,
    UniverseEvaluationResult,
)

# Default quote_ts for determinism when not in fixture
DEFAULT_QUOTE_TS = "2026-02-17T12:00:00Z"
# Default account settings for sizing when not in fixture
DEFAULT_ACCOUNT_SETTINGS = {"buying_power": 100000.0, "max_single_notional_pct": 0.05}


def load_fixture(fixture_path: Path) -> Dict[str, Any]:
    """Load offline proof fixture JSON (R22.8 / R25.1 schema)."""
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_ohlc_bars(data: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    """Return deterministic OHLC bars for symbol. No network. Empty list if not in fixture."""
    ohlc = data.get("ohlc_bars") or data.get("candles") or {}
    sym_upper = (symbol or "").strip().upper()
    bars = ohlc.get(sym_upper) or []
    if isinstance(bars, list):
        return bars
    return []


def get_option_chain_candidates(data: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    """Return option chain candidates for symbol with stable contract_key. No network."""
    chains = data.get("option_chain_candidates") or {}
    sym_upper = (symbol or "").strip().upper()
    candidates = chains.get(sym_upper) or []
    if isinstance(candidates, list):
        return candidates
    return []


def get_quotes(data: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """Return quotes for symbol: spot (price, bid, ask, last, volume, quote_ts) + option_quotes by contract_key."""
    quotes_map = data.get("quotes") or {}
    sym_upper = (symbol or "").strip().upper()
    spot = quotes_map.get(sym_upper) or {}
    if not isinstance(spot, dict):
        spot = {}
    out = dict(spot)
    if "quote_ts" not in out:
        out["quote_ts"] = DEFAULT_QUOTE_TS
    option_quotes = data.get("option_quotes") or {}
    sym_option = option_quotes.get(sym_upper)
    if isinstance(sym_option, dict):
        out["option_quotes"] = sym_option
    else:
        out["option_quotes"] = {}
    return out


def get_account_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return account settings for sizing. No network."""
    acc = data.get("account_settings") or {}
    if not isinstance(acc, dict):
        acc = {}
    out = dict(DEFAULT_ACCOUNT_SETTINGS)
    out.update(acc)
    return out


def build_universe_result_from_fixture(fixture_path: Path) -> UniverseEvaluationResult:
    """
    Build UniverseEvaluationResult from fixture. Used by offline_eval_proof script and tests.
    Produces code-only friendly fields (reason_code, rank_reason_codes) so persisted artifact is hygiene-compliant.
    """
    data = load_fixture(fixture_path)
    symbols: List[str] = data.get("symbols") or []
    overrides: Dict[str, Dict[str, Any]] = data.get("eval_overrides") or {}

    symbol_results: List[SymbolEvaluationResult] = []
    for sym in symbols:
        sym_upper = (sym or "").strip().upper()
        if not sym_upper:
            continue
        q = get_quotes(data, sym_upper)
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
        # R25.1: Use option_chain_candidates for stable contract_key when available
        chain_candidates = get_option_chain_candidates(data, sym_upper)
        if verdict == "ELIGIBLE" and stage_reached == "STAGE2_CHAIN":
            expiry = "2026-03-20"
            strike = 140.0
            delta = -0.25
            option_symbol = "NVDA260320P00140000"
            contract_key = "140-2026-03-20-PUT"
            if chain_candidates:
                c0 = chain_candidates[0]
                expiry = c0.get("expiry") or expiry
                strike = c0.get("strike") if c0.get("strike") is not None else strike
                delta = c0.get("delta") if c0.get("delta") is not None else delta
                option_symbol = c0.get("option_symbol") or c0.get("symbol") or option_symbol
                contract_key = c0.get("contract_key") or f"{int(strike)}-{expiry}-PUT"
            candidate_trades_list = [
                CandidateTrade(
                    strategy="CSP",
                    expiry=expiry,
                    strike=strike,
                    delta=delta,
                    credit_estimate=2.50,
                    max_loss=None,
                    why_this_trade="",
                )
            ]
            selected_contract = {
                "strategy": "CSP",
                "expiration": expiry,
                "strike": strike,
                "delta": delta,
                "credit_estimate": 2.50,
                "max_loss": None,
                "contract_key": contract_key,
                "contract": {"option_symbol": option_symbol, "strike": strike, "delta": delta},
            }
            selected_expiration = expiry

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
            fetched_at=q.get("quote_ts") or DEFAULT_QUOTE_TS,
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
