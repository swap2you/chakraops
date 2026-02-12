# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8: Strategy rationale tests — snapshot stability, regime explanation, DATA_INCOMPLETE."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from app.core.eval.strategy_rationale import (
    StrategyRationale,
    build_rationale_from_staged,
)


def test_rationale_to_dict_roundtrip() -> None:
    """StrategyRationale serializes and deserializes."""
    r = StrategyRationale(
        summary="Blocked by market regime: RISK_OFF",
        bullets=["Market regime: RISK_OFF (scores capped, verdict HOLD)"],
        failed_checks=["Blocked by market regime: RISK_OFF"],
        data_warnings=[],
    )
    d = r.to_dict()
    r2 = StrategyRationale.from_dict(d)
    assert r2.summary == r.summary
    assert r2.bullets == r.bullets
    assert r2.failed_checks == r.failed_checks


def test_build_rationale_regime_risk_off() -> None:
    """Rationale includes regime explanation when RISK_OFF."""
    stage1 = MagicMock(regime="BULL", iv_rank=45.0, stock_verdict=MagicMock(__str__=lambda _: "QUALIFIED"))
    stage2 = MagicMock(liquidity_ok=True, liquidity_reason="OK", chain_missing_fields=[])
    r = build_rationale_from_staged(
        symbol="SPY",
        verdict="HOLD",
        primary_reason="Blocked by market regime: RISK_OFF",
        stage1=stage1,
        stage2=stage2,
        market_regime="RISK_OFF",
        score=50,
        data_completeness=1.0,
        missing_fields=[],
    )
    assert "RISK_OFF" in r.summary or any("RISK_OFF" in b for b in r.bullets)
    assert any("RISK_OFF" in f for f in r.failed_checks)


def test_build_rationale_data_incomplete() -> None:
    """DATA_INCOMPLETE produces data_warnings and failed_checks."""
    stage1 = MagicMock(regime="NEUTRAL", iv_rank=50.0)
    stage2 = MagicMock(liquidity_ok=False, liquidity_reason="Missing bid", chain_missing_fields=["bid", "ask"])
    r = build_rationale_from_staged(
        symbol="AAPL",
        verdict="HOLD",
        primary_reason="DATA_INCOMPLETE: missing bid, ask",
        stage1=stage1,
        stage2=stage2,
        market_regime="NEUTRAL",
        score=60,
        data_completeness=0.6,
        missing_fields=["bid", "ask"],
    )
    assert len(r.data_warnings) >= 1 or len(r.failed_checks) >= 1
    assert "missing" in r.summary.lower() or any("missing" in w.lower() for w in r.data_warnings)


def test_build_rationale_snapshot_stability() -> None:
    """Same inputs produce same rationale summary and structure."""
    stage1 = MagicMock(regime="BULL", iv_rank=42.0, stock_verdict=MagicMock(__str__=lambda _: "QUALIFIED"))
    stage2 = MagicMock(liquidity_ok=True, liquidity_reason="OK", chain_missing_fields=[])
    r1 = build_rationale_from_staged(
        symbol="SPY",
        verdict="ELIGIBLE",
        primary_reason="All checks passed",
        stage1=stage1,
        stage2=stage2,
        market_regime="RISK_ON",
        score=80,
        data_completeness=1.0,
        missing_fields=[],
    )
    r2 = build_rationale_from_staged(
        symbol="SPY",
        verdict="ELIGIBLE",
        primary_reason="All checks passed",
        stage1=stage1,
        stage2=stage2,
        market_regime="RISK_ON",
        score=80,
        data_completeness=1.0,
        missing_fields=[],
    )
    assert r1.summary == r2.summary
    assert r1.bullets == r2.bullets
    assert r1.failed_checks == r2.failed_checks
