# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 Final Closure Batches D/E — universe perf, CSP action, score basis, null honesty."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_universe_list_skips_request_time_technicals(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import ui_routes as ui

    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("must not rebuild technicals on fast list")

    monkeypatch.setattr(ui, "_build_technicals_at_request_time", _boom)
    monkeypatch.setattr(ui, "_build_mtf_levels_at_request_time", _boom)

    art = SimpleNamespace(
        symbols=[
            SimpleNamespace(
                symbol="NVDA",
                verdict="HOLD",
                final_verdict="HOLD",
                score=50,
                raw_score=50,
                band="C",
                primary_reason="x",
                stage_status="STAGE1_ONLY",
                provider_status="OK",
                data_freshness=None,
                strategy=None,
                price=100.0,
                expiration=None,
                score_breakdown=None,
                band_reason=None,
                max_loss=None,
                underlying_price=100.0,
                capital_required=None,
                expected_credit=None,
                premium_yield_pct=None,
                market_cap=None,
                rank_score=None,
                score_caps=None,
                final_score=50,
                pre_cap_score=50,
            )
        ],
        selected_candidates=[],
        diagnostics_by_symbol={},
        metadata={},
    )
    rows = ui._build_universe_symbols_list(art, enrich_shares=False)
    assert called["n"] == 0
    assert len(rows) == 1


def test_csp_open_journal_action_is_sell_to_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.portfolio.trade_ticket_r262 import build_trade_ticket

    monkeypatch.setattr(
        "app.core.portfolio.trade_ticket_r262._load_symbol_context",
        lambda *_a, **_k: {
            "verdict": "ELIGIBLE",
            "score": 70,
            "primary_reason": "ok",
            "selected_contract": {"strike": 100, "expiry": "2026-12-18", "right": "P", "contract_key": "k"},
            "price": 110.0,
        },
        raising=False,
    )
    # build_trade_ticket may have different helpers — call and assert draft when possible
    try:
        out = build_trade_ticket(symbol="SPY", strategy="CSP", action="OPEN")
    except TypeError:
        out = build_trade_ticket("SPY", "CSP", "OPEN")
    draft = out.get("journal_draft") or {}
    assert draft.get("action") == "SELL_TO_OPEN"


def test_csp_payoff_spot_null_when_omitted() -> None:
    from app.core.strategy.builder_r68 import csp_payoff

    out = csp_payoff(strike=100.0, credit=1.0)
    assert out.get("spot") is None


def test_paper_win_rate_null_when_empty() -> None:
    from app.core.paper.paper_store_r270 import paper_summary_by_month

    # Invalid month shape hits empty early-return with win_rate None
    summary = paper_summary_by_month("bad")
    assert summary["trade_count"] == 0
    assert summary["win_rate"] is None


def test_reconcile_stage1_publishes_ivr_fields() -> None:
    from app.core.eval.scoring import ScoreBreakdown, reconcile_stage1_score_breakdown

    bd = ScoreBreakdown(
        data_quality_score=80,
        regime_score=70,
        options_liquidity_score=60,
        strategy_fit_score=50,
        capital_efficiency_score=40,
        composite_score=80,
    )
    out = reconcile_stage1_score_breakdown(
        bd,
        weighted_composite=80,
        stage1_score=55,
        final_score=55,
        ivr=42.0,
        ivr_band="MID",
        baseline=50.0,
        ivr_adjustment=5.0,
        data_completeness=0.9,
    )
    assert out["score_basis"] == "stage1_score"
    assert out["ivr"] == 42.0
    assert out["ivr_band"] == "MID"
