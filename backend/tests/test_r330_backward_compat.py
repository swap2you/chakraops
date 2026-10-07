"""R33.0 — backward compatibility.

The canonical decision engine is additive: it must not break existing imports
or change existing public contracts. Any intentional contract change is
documented in the R33 release notes.
"""
import importlib


def test_existing_modules_still_import():
    # Touched-in-R32 data modules and core eval/ranking modules still import.
    for name in (
        "app.core.data.orats_client",
        "app.core.data.symbol_snapshot_service",
        "app.core.data_reliability.freshness",
        "app.api.server",
    ):
        assert importlib.import_module(name) is not None


def test_decision_engine_is_isolated_namespace():
    eng = importlib.import_module("app.core.decision_engine.engine")
    assert hasattr(eng, "evaluate")
    assert hasattr(eng, "evaluate_candidate")


def test_canonical_output_contract_is_complete():
    from app.core.decision_engine.contract import DecisionOutput

    out = DecisionOutput(
        symbol="AAA", strategy="CSP", profile="balanced", market_regime="BULL",
        decision_status="ACTIONABLE", eligibility=True, data_quality="OK",
    ).to_dict()
    required = {
        "symbol", "strategy", "profile", "market_regime", "data_quality",
        "data_freshness", "event_risk", "eligibility", "selected_contract",
        "sizing", "capital_required", "expected_return_pct", "expected_return_dollars",
        "risk_flags", "score", "rank", "reason_codes", "decision_status", "manual_only",
    }
    assert required.issubset(set(out.keys()))
