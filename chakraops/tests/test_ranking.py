# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2A Tests: Ranking service — opportunity ordering, capital efficiency, strategy exclusivity."""

from __future__ import annotations

import pytest

from app.core.ranking.service import (
    rank_opportunities,
    _get_band,
    _get_primary_strategy,
    _compute_capital_required,
    _build_rank_reason,
)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------


def _make_symbol(
    symbol: str,
    verdict: str = "ELIGIBLE",
    score: int = 80,
    band: str = "A",
    price: float = 100.0,
    liquidity_ok: bool = True,
    position_open: bool = False,
    candidate_trades: list | None = None,
    csp_notional: float | None = None,
    capital_hint: dict | None = None,
    score_breakdown: dict | None = None,
    stage_reached: str = "STAGE2_CHAIN",
) -> dict:
    if capital_hint is None:
        capital_hint = {"band": band, "suggested_capital_pct": 0.05}
    if score_breakdown is None:
        score_breakdown = {"composite_score": score}
    if candidate_trades is None:
        candidate_trades = [
            {"strategy": "CSP", "strike": price * 0.9, "expiry": "2026-03-21", "credit_estimate": 2.50, "delta": -0.20}
        ]
    return {
        "symbol": symbol,
        "verdict": verdict,
        "score": score,
        "price": price,
        "liquidity_ok": liquidity_ok,
        "position_open": position_open,
        "candidate_trades": candidate_trades,
        "csp_notional": csp_notional or (candidate_trades[0]["strike"] * 100 if candidate_trades and candidate_trades[0].get("strike") else None),
        "capital_hint": capital_hint,
        "score_breakdown": score_breakdown,
        "primary_reason": f"{symbol} is eligible",
        "data_completeness": 0.95,
        "stage_reached": stage_reached,
        "rank_reasons": {"reasons": ["Eligible"], "penalty": None},
    }


# ---------------------------------------------------------------------------
# Band extraction
# ---------------------------------------------------------------------------


def test_get_band_from_capital_hint() -> None:
    sym = {"capital_hint": {"band": "B", "suggested_capital_pct": 0.05}}
    assert _get_band(sym) == "B"


def test_get_band_fallback_to_score() -> None:
    assert _get_band({"score": 85}) == "A"
    assert _get_band({"score": 70}) == "B"
    assert _get_band({"score": 50}) == "C"


# ---------------------------------------------------------------------------
# Strategy exclusivity
# ---------------------------------------------------------------------------


def test_primary_strategy_csp() -> None:
    """CSP takes priority when available."""
    sym = {"candidate_trades": [
        {"strategy": "CSP", "strike": 50},
        {"strategy": "CC", "strike": 55},
    ], "position_open": False}
    assert _get_primary_strategy(sym) == "CSP"


def test_primary_strategy_cc_needs_position() -> None:
    """CC only selected if position_open is True."""
    sym_no_pos = {"candidate_trades": [
        {"strategy": "CC", "strike": 55},
    ], "position_open": False}
    assert _get_primary_strategy(sym_no_pos) is None

    sym_with_pos = {"candidate_trades": [
        {"strategy": "CC", "strike": 55},
    ], "position_open": True}
    assert _get_primary_strategy(sym_with_pos) == "CC"


def test_primary_strategy_stock_fallback() -> None:
    """STOCK used when no CSP or CC available."""
    sym = {"candidate_trades": [
        {"strategy": "STOCK"},
    ], "position_open": False}
    assert _get_primary_strategy(sym) == "STOCK"


def test_primary_strategy_none_for_hold() -> None:
    """No strategy for HOLD-only candidates."""
    sym = {"candidate_trades": [
        {"strategy": "HOLD"},
    ], "position_open": False}
    assert _get_primary_strategy(sym) is None


def test_strategy_exclusivity_never_both_csp_cc() -> None:
    """If CSP and CC are both available, only CSP is returned."""
    sym = {"candidate_trades": [
        {"strategy": "CSP", "strike": 50},
        {"strategy": "CC", "strike": 55},
    ], "position_open": True}
    # CSP takes priority even if position is open
    assert _get_primary_strategy(sym) == "CSP"


# ---------------------------------------------------------------------------
# Capital computation
# ---------------------------------------------------------------------------


def test_compute_capital_csp() -> None:
    """CSP capital = strike * 100."""
    sym = {}
    trade = {"strategy": "CSP", "strike": 250}
    assert _compute_capital_required(sym, "CSP", trade) == 25000.0


def test_compute_capital_csp_from_selected_contract() -> None:
    """CSP capital from selected_contract when trade has no strike."""
    sym = {"selected_contract": {"contract": {"strike": 300}}}
    trade = {"strategy": "CSP"}
    assert _compute_capital_required(sym, "CSP", trade) == 30000.0


def test_compute_capital_stock() -> None:
    """STOCK capital = price * 100 shares."""
    sym = {"price": 150.0}
    assert _compute_capital_required(sym, "STOCK", None) == 15000.0


# ---------------------------------------------------------------------------
# Ranking order correctness
# ---------------------------------------------------------------------------


def test_ranking_band_priority() -> None:
    """Band A ranks above Band B, regardless of score."""
    symbols = [
        _make_symbol("LOW_A", score=60, band="A"),
        _make_symbol("HIGH_B", score=95, band="B"),
        _make_symbol("MED_C", score=75, band="C"),
    ]
    ranked = rank_opportunities(symbols, account_equity=100000, limit=10)
    assert len(ranked) == 3
    assert ranked[0]["symbol"] == "LOW_A"
    assert ranked[1]["symbol"] == "HIGH_B"
    assert ranked[2]["symbol"] == "MED_C"


def test_ranking_score_within_same_band() -> None:
    """Within same band, higher score ranks first."""
    symbols = [
        _make_symbol("LOW", score=70, band="A"),
        _make_symbol("HIGH", score=90, band="A"),
        _make_symbol("MED", score=80, band="A"),
    ]
    ranked = rank_opportunities(symbols, account_equity=100000, limit=10)
    assert ranked[0]["symbol"] == "HIGH"
    assert ranked[1]["symbol"] == "MED"
    assert ranked[2]["symbol"] == "LOW"


def test_ranking_capital_efficiency_tiebreak() -> None:
    """Same band and score: lower capital_pct ranks first."""
    symbols = [
        _make_symbol("EXPENSIVE", score=80, band="A", price=500),  # strike ~450, notional 45k
        _make_symbol("CHEAP", score=80, band="A", price=25),       # strike ~22.5, notional 2.25k
    ]
    ranked = rank_opportunities(symbols, account_equity=100000, limit=10)
    # CHEAP has lower capital_pct (2.25k/100k vs 45k/100k)
    assert ranked[0]["symbol"] == "CHEAP"
    assert ranked[1]["symbol"] == "EXPENSIVE"


def test_ranking_only_eligible() -> None:
    """HOLD and BLOCKED symbols are excluded."""
    symbols = [
        _make_symbol("ELIG", verdict="ELIGIBLE"),
        _make_symbol("HOLD", verdict="HOLD"),
        _make_symbol("BLOCK", verdict="BLOCKED"),
    ]
    ranked = rank_opportunities(symbols, limit=10)
    assert len(ranked) == 1
    assert ranked[0]["symbol"] == "ELIG"


def test_ranking_limit() -> None:
    """Limit parameter controls max results."""
    symbols = [_make_symbol(f"SYM{i}", score=90 - i) for i in range(10)]
    ranked = rank_opportunities(symbols, limit=3)
    assert len(ranked) == 3
    assert ranked[0]["rank"] == 1


def test_ranking_strategy_filter() -> None:
    """Strategy filter excludes non-matching strategies."""
    symbols = [
        _make_symbol("CSP_SYM", candidate_trades=[{"strategy": "CSP", "strike": 50}]),
        _make_symbol("STOCK_SYM", candidate_trades=[{"strategy": "STOCK"}]),
    ]
    ranked = rank_opportunities(symbols, strategy_filter="CSP", limit=10)
    assert len(ranked) == 1
    assert ranked[0]["symbol"] == "CSP_SYM"


def test_ranking_max_capital_pct_filter() -> None:
    """Max capital % filter excludes expensive opportunities."""
    symbols = [
        _make_symbol("CHEAP", price=10),   # strike ~9, notional 900, pct=0.9%
        _make_symbol("PRICEY", price=500),  # strike ~450, notional 45000, pct=45%
    ]
    ranked = rank_opportunities(symbols, account_equity=100000, max_capital_pct=0.05, limit=10)
    assert len(ranked) == 1
    assert ranked[0]["symbol"] == "CHEAP"


def test_ranking_assigns_ranks() -> None:
    """Each opportunity gets a sequential rank."""
    symbols = [
        _make_symbol("A", score=90),
        _make_symbol("B", score=80),
        _make_symbol("C", score=70),
    ]
    ranked = rank_opportunities(symbols, limit=10)
    assert [o["rank"] for o in ranked] == [1, 2, 3]


def test_ranking_capital_pct_with_no_equity() -> None:
    """When no account equity, capital_pct is None."""
    symbols = [_make_symbol("SYM")]
    ranked = rank_opportunities(symbols, account_equity=None, limit=10)
    assert ranked[0]["capital_pct"] is None


def test_ranking_output_structure() -> None:
    """Verify all expected fields in ranked opportunity."""
    symbols = [_make_symbol("TEST", price=50)]
    ranked = rank_opportunities(symbols, account_equity=100000, limit=5)
    assert len(ranked) == 1
    opp = ranked[0]
    required_fields = [
        "rank", "symbol", "strategy", "band", "score",
        "capital_required", "capital_pct", "rank_reason",
        "primary_reason", "price", "strike", "expiry",
        "credit_estimate", "delta", "liquidity_ok",
        "position_open", "score_breakdown", "rank_reasons",
    ]
    for field in required_fields:
        assert field in opp, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Rank reason
# ---------------------------------------------------------------------------


def test_build_rank_reason() -> None:
    reason = _build_rank_reason("A", 85, "CSP", 0.03, True, "eligible")
    assert "Band A" in reason
    assert "score 85" in reason
    assert "efficient" in reason


def test_build_rank_reason_high_capital() -> None:
    reason = _build_rank_reason("B", 70, "CSP", 0.15, True, "eligible")
    assert "15%" in reason


def test_build_rank_reason_low_liquidity() -> None:
    reason = _build_rank_reason("A", 80, "CSP", 0.05, False, "eligible")
    assert "liquidity" in reason.lower()
