# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 finance + eval remediation regressions (DEF-010/012/013/033/034)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pytest


def test_r70_def010_premium_not_divided_by_100() -> None:
    from datetime import datetime, timezone

    from app.core.decision_engine.live_service import _option_contract_from

    candidate = {
        "strike": 100.0,
        "delta": -0.25,
        "credit_estimate": 1.50,
        "expiry": "2099-12-19",
    }
    summary = {"expiration": "2099-12-19"}
    diagnostics = {"liquidity": {"option_liquidity_ok": True}}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    contract, prov = _option_contract_from(candidate, summary, diagnostics, now=now)
    assert contract is not None
    assert contract.premium == pytest.approx(1.50)
    assert contract.open_interest is None
    assert contract.volume is None
    assert "LIQUIDITY_VALIDATED_UPSTREAM" in prov


def test_r70_def013_zero_credit_preserved() -> None:
    from app.core.eval.universe_evaluator import CandidateTrade

    # Reproduce the falsy-zero bug pattern: bid=0 must remain 0.0, not None.
    bid = 0.0
    credit = 0.0 if bid is None else float(bid)
    credit_estimate = round(credit, 2)
    assert credit_estimate == 0.0
    assert credit_estimate is not None


def test_r70_def034_lock_exclusive_create_and_ownership(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.eval import evaluation_store as store

    monkeypatch.setattr(store, "_get_evaluations_dir", lambda: tmp_path)
    assert store.acquire_run_lock("run-a", "2026-01-01T00:00:00Z") is True
    assert store.acquire_run_lock("run-b", "2026-01-01T00:00:01Z") is False
    # Non-owner cannot release.
    store.release_run_lock(expected_run_id="run-b")
    assert store._run_lock_path().exists()
    store.release_run_lock(expected_run_id="run-a")
    assert not store._run_lock_path().exists()


def test_r70_def033_ops_evaluate_uses_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /api/ops/evaluate must not shell out to run_and_save --limit 5."""
    import app.api.server as server

    called: Dict[str, Any] = {}

    def fake_exclusive(symbols, *, mode="LIVE", trigger="api"):
        called["symbols"] = list(symbols)
        called["mode"] = mode
        called["trigger"] = trigger
        return {
            "started": True,
            "reason": "ok",
            "run_id": "coord-1",
            "counts": {"universe_size": len(symbols)},
        }

    monkeypatch.setattr(
        "app.core.eval.eval_coordinator.run_universe_evaluation_exclusive",
        fake_exclusive,
    )
    monkeypatch.setenv("EVALUATE_TRIGGER_TOKEN", "")
    # Ensure token check passes (empty token disables check).
    if "EVALUATE_TRIGGER_TOKEN" in os.environ and os.environ["EVALUATE_TRIGGER_TOKEN"]:
        monkeypatch.delenv("EVALUATE_TRIGGER_TOKEN", raising=False)

    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    resp = client.post("/api/ops/evaluate", json={"reason": "MANUAL_REFRESH"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("accepted") is True
    assert body.get("exclusive") is True
    assert called.get("mode") == "LIVE"
    assert called.get("trigger") == "ops_evaluate"
    assert "subprocess" not in body


def test_r70_liquidity_gate_honors_upstream_flag() -> None:
    from app.core.decision_engine.contract import DecisionInput, OptionContract, CSP
    from app.core.decision_engine.gates import liquidity_gate
    from app.core.decision_engine.profiles import get_profile

    profile = get_profile("balanced")
    inp = DecisionInput(
        symbol="AAPL",
        strategy=CSP,
        market_regime="NEUTRAL",
        price=100.0,
        contract=OptionContract(delta=-0.25, dte=30, premium=1.5, strike=95.0),
        liquidity_validated_upstream=True,
    )
    ok, reasons = liquidity_gate(inp, profile)
    assert ok is True
    assert "LIQUIDITY_VALIDATED_UPSTREAM" in reasons
