# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — missing-cash and sector safety (Phase 4).

Available cash is never inferred from total equity. Cash-consuming CSP and
share-buy recommendations are blocked/non-actionable when available cash is
unknown. Covered calls (which need owned shares, not cash) may still proceed.
Sector concentration that cannot be evaluated is surfaced explicitly, never
silently ignored.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.decision_engine.contract import PortfolioState
from app.core.decision_engine.live_service import (
    cash_is_known,
    compute_live_recommendations,
    portfolio_state_from_metrics,
)
from app.core.eval.decision_artifact_v2 import (
    CandidateRow,
    DecisionArtifactV2,
    EarningsInfo,
    SymbolDiagnosticsDetails,
    SymbolEvalSummary,
)

NOW = datetime(2026, 6, 21, 16, 0, 0, tzinfo=timezone.utc)


def _build(symbols=("AAPL",), *, strategy="CSP", as_of=None):
    as_of = as_of or NOW.isoformat()
    expiration = (NOW + timedelta(days=33)).date().isoformat()
    summaries = [
        SymbolEvalSummary(
            symbol=s, verdict="ELIGIBLE", final_verdict="ELIGIBLE", score=92, band="A",
            primary_reason=None, stage_status="RUN", stage1_status="PASS", stage2_status="PASS",
            provider_status="OK", data_freshness=as_of, evaluated_at=as_of, strategy=strategy,
            price=100.0, expiration=expiration, has_candidates=True, candidate_count=1,
            underlying_price=100.0, expected_credit=200.0,
        )
        for s in symbols
    ]
    selected = [
        CandidateRow(symbol=s, strategy=strategy, expiry=expiration, strike=100.0, delta=0.22,
                     credit_estimate=200.0, max_loss=10000.0)
        for s in symbols
    ]
    return DecisionArtifactV2(
        metadata={"run_id": "cash-test", "pipeline_timestamp": as_of},
        symbols=summaries,
        selected_candidates=selected,
        candidates_by_symbol={s: [selected[i]] for i, s in enumerate(symbols)},
        gates_by_symbol={},
        earnings_by_symbol={s: EarningsInfo(earnings_days=30, earnings_block=False, note=None) for s in symbols},
        diagnostics_by_symbol={s: SymbolDiagnosticsDetails(
            technicals={}, exit_plan={}, risk_flags={}, explanation={}, stock={"price": 100.0},
            symbol_eligibility={}, liquidity={"option_liquidity_ok": True}, regime="NEUTRAL",
        ) for s in symbols},
    )


def _actionable_symbols(res):
    return {it["symbol"] for it in res["recommendations"]["actionable"]}


def test_cash_is_known_does_not_infer_from_equity() -> None:
    assert cash_is_known({"total_equity": 100000}, {}) is False
    assert cash_is_known({}, {"cash": 50000}) is True


def test_portfolio_state_unknown_cash_is_zero_not_equity() -> None:
    ps = portfolio_state_from_metrics({"total_equity": 1_000_000}, {})
    assert ps.total_value == 1_000_000.0
    assert ps.available_cash == 0.0  # fail-closed: not inferred from equity


def test_missing_cash_blocks_csp(monkeypatch) -> None:
    art = _build(["AAPL"], strategy="CSP")
    res = compute_live_recommendations(
        art, profile_name="balanced", guardrails_metrics={"total_equity": 1_000_000}, guardrails_snapshot={}, now=NOW
    )
    # CSP is cash-consuming; with unknown cash it must not be actionable.
    assert "AAPL" not in _actionable_symbols(res)
    assert res["cash_known"] is False
    assert "AVAILABLE_CASH_UNKNOWN" in res["data_flags"]
    cs = res["capital_safety"]
    assert cs["cash_known"] is False
    assert "AVAILABLE_CASH_UNKNOWN" in cs["flags"]


def test_known_cash_allows_csp_actionable() -> None:
    art = _build(["AAPL"], strategy="CSP")
    res = compute_live_recommendations(
        art, profile_name="balanced", portfolio=PortfolioState(total_value=1_000_000.0, available_cash=500_000.0), now=NOW
    )
    assert res["cash_known"] is True
    assert "AAPL" in _actionable_symbols(res)


def test_covered_call_proceeds_without_cash() -> None:
    art = _build(["AAPL"], strategy="COVERED_CALL")
    res = compute_live_recommendations(
        art, profile_name="balanced", guardrails_metrics={"total_equity": 1_000_000}, guardrails_snapshot={},
        shares_by_symbol={"AAPL": 100}, now=NOW
    )
    # CC needs owned shares (not cash); it can still be actionable.
    assert "AAPL" in _actionable_symbols(res)


def test_sector_unavailable_blocks_incremental_csp() -> None:
    # ZZZZ has no approved sector mapping -> incremental CSP exposure is BLOCKED,
    # never silently sized past the sector cap.
    art = _build(["ZZZZ"], strategy="CSP")
    res = compute_live_recommendations(
        art, profile_name="balanced", portfolio=PortfolioState(total_value=1_000_000.0, available_cash=500_000.0), now=NOW
    )
    assert "ZZZZ" not in _actionable_symbols(res)
    blocked = [b for b in res["recommendations"]["blocked"] if b["symbol"] == "ZZZZ"]
    assert blocked
    assert "SECTOR_DATA_UNAVAILABLE" in blocked[0]["reason_codes"]


def test_known_sector_csp_is_actionable() -> None:
    # AAPL maps to a known sector with no existing exposure -> below cap -> allowed.
    art = _build(["AAPL"], strategy="CSP")
    res = compute_live_recommendations(
        art, profile_name="balanced", portfolio=PortfolioState(total_value=1_000_000.0, available_cash=500_000.0), now=NOW
    )
    assert "AAPL" in _actionable_symbols(res)


def test_aggregate_displayed_capital_present() -> None:
    art = _build(["AAPL"], strategy="CSP")
    res = compute_live_recommendations(
        art, profile_name="balanced", portfolio=PortfolioState(total_value=1_000_000.0, available_cash=500_000.0), now=NOW
    )
    cs = res["capital_safety"]
    assert "total_capital_required_displayed" in cs
    assert cs["per_suggestion_not_additive"] is True
