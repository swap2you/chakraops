"""R33.0 — canonical decision contract shape (backward-compatibility anchor).

These assertions pin the canonical output keys so future contract changes are
intentional and documented.
"""
from app.core.decision_engine.contract import (
    DecisionInput,
    DecisionOutput,
    OptionContract,
    PortfolioState,
    Sizing,
)

EXPECTED_OUTPUT_KEYS = {
    "symbol",
    "strategy",
    "profile",
    "market_regime",
    "decision_status",
    "eligibility",
    "data_quality",
    "data_freshness",
    "event_risk",
    "selected_contract",
    "sizing",
    "capital_required",
    "expected_return_pct",
    "expected_return_dollars",
    "risk_flags",
    "score",
    "rank",
    "reason_codes",
    "manual_only",
}


def test_decision_output_contract_keys_are_stable():
    out = DecisionOutput(
        symbol="AAA",
        strategy="CSP",
        profile="balanced",
        market_regime="BULL",
        decision_status="ACTIONABLE",
        eligibility=True,
        data_quality="OK",
    )
    assert set(out.to_dict().keys()) == EXPECTED_OUTPUT_KEYS


def test_manual_only_defaults_true():
    out = DecisionOutput(
        symbol="AAA", strategy="CSP", profile="balanced", market_regime="BULL",
        decision_status="ACTIONABLE", eligibility=True, data_quality="OK",
    )
    assert out.to_dict()["manual_only"] is True


def test_input_and_nested_dataclasses_serialize():
    inp = DecisionInput(
        symbol="AAA",
        strategy="CSP",
        market_regime="BULL",
        price=100.0,
        contract=OptionContract(delta=0.2, dte=30, premium=2.0, strike=100.0),
    )
    d = inp.to_dict()
    assert d["symbol"] == "AAA"
    assert d["contract"]["strike"] == 100.0
    assert PortfolioState(total_value=1.0, available_cash=1.0).to_dict()["total_value"] == 1.0
    assert Sizing(contracts=2).to_dict()["contracts"] == 2
