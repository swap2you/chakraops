# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.1 — API contract: /api/ui/action-needed items carry an additive explanation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.server import app
from app.core.eval.decision_artifact_v2 import (
    CandidateRow,
    DecisionArtifactV2,
    EarningsInfo,
    SymbolDiagnosticsDetails,
    SymbolEvalSummary,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _artifact(symbols=("AAPL",), *, as_of=None):
    as_of = as_of or _now().isoformat()
    expiration = (_now() + timedelta(days=33)).date().isoformat()
    summaries = [
        SymbolEvalSummary(
            symbol=s, verdict="ELIGIBLE", final_verdict="ELIGIBLE", score=92, band="A",
            primary_reason=None, stage_status="RUN", stage1_status="PASS", stage2_status="PASS",
            provider_status="OK", data_freshness=as_of, evaluated_at=as_of, strategy="CSP",
            price=100.0, expiration=expiration, has_candidates=True, candidate_count=1,
            underlying_price=100.0, expected_credit=200.0,
        )
        for s in symbols
    ]
    selected = [
        CandidateRow(symbol=s, strategy="CSP", expiry=expiration, strike=100.0, delta=0.22,
                     credit_estimate=200.0, max_loss=10000.0)
        for s in symbols
    ]
    return DecisionArtifactV2(
        metadata={"run_id": "r361-test", "pipeline_timestamp": as_of},
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


class _FakeStore:
    def __init__(self, artifact):
        self._a = artifact

    def reload_from_disk(self):
        pass

    def get_latest(self):
        return self._a

    def get_symbol(self, sym):
        return None


def _patch_store(monkeypatch, artifact):
    monkeypatch.setattr(
        "app.core.eval.evaluation_store_v2.get_evaluation_store_v2",
        lambda: _FakeStore(artifact),
    )
    monkeypatch.setattr("app.core.eval.evaluation_store_v2.get_eval_snapshot", lambda: {})
    monkeypatch.setattr("app.api.ui_routes._require_ui_key", lambda *a, **k: None)


def _all_items(auth):
    items = []
    for bucket in ("actionable", "watch", "blocked"):
        items.extend(auth.get(bucket) or [])
    return items


def test_action_needed_items_carry_explanation(monkeypatch):
    _patch_store(monkeypatch, _artifact())
    data = TestClient(app).get("/api/ui/action-needed").json()
    auth = data["authoritative_recommendations"]

    items = _all_items(auth)
    # At least one recommendation bucket item OR a stay_in_cash sentinel must exist.
    sic = auth.get("stay_in_cash")
    assert items or isinstance(sic, dict)

    for item in items:
        exp = item.get("explanation")
        assert exp is not None, f"missing explanation on {item.get('symbol')}"
        assert exp["symbol"] == item.get("symbol")
        assert exp["decision_status"] == item.get("decision_status")
        assert exp["manual_only"] is True
        assert exp["trade_execution"] is False
        assert "near_miss" in exp
        assert isinstance(exp["supporting_reasons"], list)

    if isinstance(sic, dict):
        assert "explanation" in sic


def test_legacy_item_keys_unchanged(monkeypatch):
    """Additive: existing item keys must still be present (no regression)."""
    _patch_store(monkeypatch, _artifact())
    data = TestClient(app).get("/api/ui/action-needed").json()
    auth = data["authoritative_recommendations"]
    items = _all_items(auth)
    if not items:
        return
    item = items[0]
    for key in ("symbol", "strategy", "decision_status", "next_action_code",
                "reason_codes", "risk_flags", "manual_only", "authoritative", "recommended_by"):
        assert key in item


def test_no_raw_fail_warn_in_explanation(monkeypatch):
    _patch_store(monkeypatch, _artifact())
    data = TestClient(app).get("/api/ui/action-needed").json()
    auth = data["authoritative_recommendations"]
    for item in _all_items(auth):
        text = str(item.get("explanation") or {})
        assert "FAIL_" not in text
        assert "WARN_" not in text


def test_explanation_never_adds_broker_surface(monkeypatch):
    _patch_store(monkeypatch, _artifact())
    data = TestClient(app).get("/api/ui/action-needed").json()
    assert data.get("authoritative_recommendations", {}).get("manual_only") is True
    for item in _all_items(data["authoritative_recommendations"]):
        exp = item.get("explanation") or {}
        assert exp.get("trade_execution") is False
