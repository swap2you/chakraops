# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — live sector enforcement (Phase 3).

Sectors are mapped from approved local company metadata and existing sector
exposure is derived from the portfolio. Profile sector caps are enforced for
incremental cash-consuming exposure (CSP / share buy); unavailable sector data
BLOCKS incremental exposure rather than silently bypassing the cap. Covered
calls on already-owned shares may proceed with an explicit data-gap flag.
"""

from __future__ import annotations

from app.core.decision_engine import gates as G
from app.core.decision_engine import sizing as S
from app.core.decision_engine.contract import (
    CSP,
    COVERED_CALL,
    DecisionInput,
    OptionContract,
    PortfolioState,
    SHARE_BUY,
)
from app.core.decision_engine.live_service import portfolio_state_from_metrics
from app.core.decision_engine.profiles import get_profile

PROFILE = get_profile("balanced")  # max_sector_exposure_pct default 35
TOTAL = 1_000_000.0
SECTOR_CAP = TOTAL * PROFILE.max_sector_exposure_pct / 100.0  # 350,000


def _csp(symbol="AAPL", sector="Technology"):
    return DecisionInput(
        symbol=symbol, strategy=CSP, market_regime="NEUTRAL", price=100.0,
        contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=100.0),
        sector=sector,
    )


# --- sector_gate: known sector below / at / above cap ----------------------

def test_known_sector_below_limit_passes() -> None:
    pf = PortfolioState(total_value=TOTAL, available_cash=500_000.0, sector_exposure={"Technology": 100_000.0})
    ok, reasons = G.sector_gate(_csp(), PROFILE, pf)
    assert ok is True
    assert reasons == []


def test_known_sector_at_limit_blocks() -> None:
    pf = PortfolioState(total_value=TOTAL, available_cash=500_000.0, sector_exposure={"Technology": SECTOR_CAP})
    ok, reasons = G.sector_gate(_csp(), PROFILE, pf)
    assert ok is False
    assert "SECTOR_EXPOSURE_LIMIT_REACHED" in reasons


def test_known_sector_above_limit_blocks() -> None:
    pf = PortfolioState(total_value=TOTAL, available_cash=500_000.0, sector_exposure={"Technology": SECTOR_CAP + 50_000.0})
    ok, reasons = G.sector_gate(_csp(), PROFILE, pf)
    assert ok is False
    assert "SECTOR_EXPOSURE_LIMIT_REACHED" in reasons


def test_unavailable_sector_blocks_csp() -> None:
    pf = PortfolioState(total_value=TOTAL, available_cash=500_000.0)
    ok, reasons = G.sector_gate(_csp(sector=None), PROFILE, pf)
    assert ok is False
    assert "SECTOR_DATA_UNAVAILABLE" in reasons
    assert "SECTOR_BLOCKED_PENDING_DATA" in reasons


def test_unavailable_sector_blocks_share_buy() -> None:
    pf = PortfolioState(total_value=TOTAL, available_cash=500_000.0)
    inp = DecisionInput(symbol="ZZZZ", strategy=SHARE_BUY, market_regime="NEUTRAL", price=50.0, sector=None)
    ok, reasons = G.sector_gate(inp, PROFILE, pf)
    assert ok is False
    assert "SECTOR_DATA_UNAVAILABLE" in reasons


def test_covered_call_exempt_from_sector_gate() -> None:
    pf = PortfolioState(total_value=TOTAL, available_cash=0.0)
    inp = DecisionInput(symbol="AAPL", strategy=COVERED_CALL, market_regime="NEUTRAL", price=100.0, sector=None, shares_held=100)
    ok, reasons = G.sector_gate(inp, PROFILE, pf)
    assert ok is True


# --- sizing: headroom math + existing-position covered-call flag -------------

def test_sizing_caps_budget_to_sector_headroom() -> None:
    # Existing sector exposure 300k -> headroom 50k -> at most 5 CSP contracts
    # (collateral 10k each) regardless of larger cash.
    pf = PortfolioState(total_value=TOTAL, available_cash=900_000.0, sector_exposure={"Technology": 300_000.0})
    res = S.size_csp(_csp(), PROFILE, pf)
    assert res.capital_required <= 50_000.0 + 1e-6
    assert "SECTOR_CAP_ENFORCED" in res.risk_flags


def test_sizing_symbol_headroom_caps_budget() -> None:
    # max_symbol_exposure_pct default 20 -> symbol cap 200k; existing 150k -> 50k.
    pf = PortfolioState(
        total_value=TOTAL, available_cash=900_000.0,
        symbol_exposure={"AAPL": 150_000.0}, sector_exposure={"Technology": 0.0},
    )
    res = S.size_csp(_csp(), PROFILE, pf)
    assert res.capital_required <= 50_000.0 + 1e-6


def test_covered_call_unavailable_sector_continues_with_flag() -> None:
    pf = PortfolioState(total_value=TOTAL, available_cash=0.0)
    inp = DecisionInput(symbol="ZZZZ", strategy=COVERED_CALL, market_regime="NEUTRAL", price=100.0, sector=None, shares_held=200)
    res = S.size_covered_call(inp, PROFILE, pf)
    assert res.sizing.contracts == 2  # 200 shares -> 2 lots, still proceeds
    assert "SECTOR_DATA_UNAVAILABLE_EXISTING_POSITION" in res.risk_flags


# --- portfolio sector exposure derivation -----------------------------------

def test_portfolio_state_derives_sector_exposure_from_symbols() -> None:
    ps = portfolio_state_from_metrics(
        {"total_equity": TOTAL, "cash": 100_000.0, "symbol_notionals": {"AAPL": 120_000.0, "MSFT": 80_000.0}},
        {},
    )
    # AAPL + MSFT are both Technology -> aggregated sector exposure.
    assert ps.sector_exposure.get("Technology") == 200_000.0
