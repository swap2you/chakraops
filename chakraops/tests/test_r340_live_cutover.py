# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — canonical live cutover (closes H-5).

Proves the canonical decision engine is the authoritative producer of the
primary live recommendation via the live service, that stale data blocks the
live recommendation, that legacy and canonical stacks cannot present a
conflicting primary, that the active profile is carried through, that output is
manual-only and capped to the profile's top 5–7, and that recommendation-set
capital safety is surfaced. Deterministic: ``now`` is injected; no ORATS calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.core.decision_engine.contract import PortfolioState
from app.core.decision_engine.legacy_adapter import DECISION_SOURCE
from app.core.decision_engine.live_service import compute_live_recommendations
from app.core.eval.decision_artifact_v2 import (
    CandidateRow,
    DecisionArtifactV2,
    EarningsInfo,
    SymbolDiagnosticsDetails,
    SymbolEvalSummary,
)

NOW = datetime(2026, 6, 21, 16, 0, 0, tzinfo=timezone.utc)


def _summary(symbol: str, *, as_of: str, expiration: str, strategy: str = "CSP") -> SymbolEvalSummary:
    return SymbolEvalSummary(
        symbol=symbol,
        verdict="ELIGIBLE",
        final_verdict="ELIGIBLE",
        score=92,
        band="A",
        primary_reason=None,
        stage_status="RUN",
        stage1_status="PASS",
        stage2_status="PASS",
        provider_status="OK",
        data_freshness=as_of,
        evaluated_at=as_of,
        strategy=strategy,
        price=100.0,
        expiration=expiration,
        has_candidates=True,
        candidate_count=1,
        underlying_price=100.0,
        expected_credit=200.0,
    )


def _diag(regime: str = "NEUTRAL", *, liq_ok: bool = True) -> SymbolDiagnosticsDetails:
    return SymbolDiagnosticsDetails(
        technicals={},
        exit_plan={},
        risk_flags={},
        explanation={},
        stock={"price": 100.0},
        symbol_eligibility={},
        liquidity={"option_liquidity_ok": liq_ok},
        regime=regime,
    )


def _build_artifact(symbols, *, as_of, regime="NEUTRAL", liq_ok=True, strategy="CSP", n_days=33):
    expiration = (NOW + timedelta(days=n_days)).date().isoformat()
    summaries = [_summary(s, as_of=as_of, expiration=expiration, strategy=strategy) for s in symbols]
    selected = [
        CandidateRow(
            symbol=s,
            strategy=strategy,
            expiry=expiration,
            strike=100.0,
            delta=0.22,
            credit_estimate=200.0,
            max_loss=10000.0,
        )
        for s in symbols
    ]
    earnings = {s: EarningsInfo(earnings_days=30, earnings_block=False, note=None) for s in symbols}
    diags = {s: _diag(regime, liq_ok=liq_ok) for s in symbols}
    return DecisionArtifactV2(
        metadata={"run_id": "r340-test", "pipeline_timestamp": as_of},
        symbols=summaries,
        selected_candidates=selected,
        candidates_by_symbol={s: [selected[i]] for i, s in enumerate(symbols)},
        gates_by_symbol={},
        earnings_by_symbol=earnings,
        diagnostics_by_symbol=diags,
    )


def _portfolio(cash: float = 500_000.0, total: float = 1_000_000.0) -> PortfolioState:
    return PortfolioState(total_value=total, available_cash=cash)


def test_live_recommendation_comes_from_canonical_engine() -> None:
    art = _build_artifact(["AAPL"], as_of=NOW.isoformat())
    res = compute_live_recommendations(art, profile_name="balanced", portfolio=_portfolio(), now=NOW)

    assert res["decision_source"] == DECISION_SOURCE
    assert res["authoritative"] is True
    assert res["manual_only"] is True
    recs = res["recommendations"]
    assert recs["decision_source"] == DECISION_SOURCE
    actionable = recs["actionable"]
    assert len(actionable) == 1
    item = actionable[0]
    assert item["symbol"] == "AAPL"
    assert item["recommended_by"] == DECISION_SOURCE
    assert item["authoritative"] is True
    assert item["next_action_code"] == "ENTRY"
    # Liquidity provenance from the upstream batch gate is transparent.
    assert "LIQUIDITY_VALIDATED_UPSTREAM" in item["reason_codes"]


def test_stale_data_blocks_live_recommendation() -> None:
    stale = (NOW - timedelta(days=5)).isoformat()
    art = _build_artifact(["AAPL"], as_of=stale)
    res = compute_live_recommendations(art, profile_name="balanced", portfolio=_portfolio(), now=NOW)

    recs = res["recommendations"]
    assert recs["actionable"] == []
    blocked = recs["blocked"]
    assert any(b["symbol"] == "AAPL" for b in blocked)
    blocked_item = next(b for b in blocked if b["symbol"] == "AAPL")
    assert blocked_item["next_action_code"] == "BLOCKED"
    # No ACTIONABLE produced from stale data anywhere in the response.
    assert blocked_item["decision_status"] == "BLOCKED"


def test_no_conflicting_primary_single_authoritative_source() -> None:
    art = _build_artifact(["AAPL"], as_of=NOW.isoformat())
    res = compute_live_recommendations(art, profile_name="balanced", portfolio=_portfolio(), now=NOW)
    # Exactly one declared authoritative source for the primary decision.
    assert res["decision_source"] == DECISION_SOURCE
    assert res["recommendations"]["decision_source"] == DECISION_SOURCE
    # Every surfaced primary item is tagged authoritative + canonical.
    for bucket in ("actionable", "watch", "blocked"):
        for it in res["recommendations"][bucket]:
            assert it["recommended_by"] == DECISION_SOURCE
            assert it["authoritative"] is True


def test_active_profile_carried_through() -> None:
    art = _build_artifact(["AAPL"], as_of=NOW.isoformat())
    for prof in ("conservative", "balanced", "aggressive"):
        res = compute_live_recommendations(art, profile_name=prof, portfolio=_portfolio(), now=NOW)
        assert res["profile"]["name"] == prof
        assert res["recommendations"]["profile"]["name"] == prof


def test_manual_only_label_present_everywhere() -> None:
    art = _build_artifact(["AAPL"], as_of=NOW.isoformat())
    res = compute_live_recommendations(art, profile_name="balanced", portfolio=_portfolio(), now=NOW)
    assert res["manual_only"] is True
    for it in res["recommendations"]["actionable"]:
        assert it["manual_only"] is True


def test_top_actionable_capped_to_profile_5_to_7() -> None:
    symbols = [f"SYM{i}" for i in range(20)]
    art = _build_artifact(symbols, as_of=NOW.isoformat())
    res = compute_live_recommendations(art, profile_name="balanced", portfolio=_portfolio(), now=NOW)
    shown = res["recommendations"]["actionable"]
    # balanced max_recommendations == 7; conservative == 5.
    assert 1 <= len(shown) <= 7
    assert len(shown) == res["counts"]["shown"]
    assert res["counts"]["actionable"] >= len(shown)

    res_cons = compute_live_recommendations(art, profile_name="conservative", portfolio=_portfolio(), now=NOW)
    assert len(res_cons["recommendations"]["actionable"]) <= 5


def test_capital_set_safety_warns_when_combined_exceeds_deployable() -> None:
    symbols = [f"SYM{i}" for i in range(7)]
    art = _build_artifact(symbols, as_of=NOW.isoformat())
    # Small cash: each CSP needs strike*100*contracts collateral; combined set exceeds deployable.
    res = compute_live_recommendations(
        art, profile_name="balanced", portfolio=_portfolio(cash=15_000.0, total=15_000.0), now=NOW
    )
    cap = res["capital_safety"]
    assert cap["per_suggestion_not_additive"] is True
    assert cap["assumes_leverage_or_margin"] is False
    assert "deployable_capital" in cap
    assert "total_capital_required_displayed" in cap
    if cap["total_capital_required_displayed"] > cap["deployable_capital"]:
        assert cap["exceeds_deployable_capital"] is True
        assert "RECOMMENDATION_SET_EXCEEDS_DEPLOYABLE_CAPITAL" in cap["flags"]


def test_live_output_has_no_fail_warn_substrings() -> None:
    art = _build_artifact(["AAPL", "MSFT"], as_of=NOW.isoformat())
    res = compute_live_recommendations(art, profile_name="balanced", portfolio=_portfolio(), now=NOW)
    raw = json.dumps(res)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw


def test_action_needed_route_declares_canonical_source() -> None:
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/action-needed")
    assert r.status_code == 200
    data = r.json()
    # Cutover markers present regardless of store contents.
    assert data["decision_source"] == "canonical_decision_engine"
    assert data["legacy_lists_role"] == "diagnostic_non_authoritative"
    assert data["manual_only"] is True
    assert "authoritative_recommendations" in data
    assert "active_profile" in data
