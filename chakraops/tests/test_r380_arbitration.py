# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 — CSP vs shares arbitration."""

from app.core.decision_engine.wheel_v2.arbitration import arbitrate_csp_vs_shares
from app.core.decision_engine.wheel_v2.contract import (
    ASSIGNMENT_INAPPROPRIATE,
    BOTH_UNATTRACTIVE,
    CASH_INSUFFICIENT,
    CSP_PREFERRED,
    SHARES_PREFERRED,
)


def _csp(score=70.0, capital=10000.0, ok=True):
    return {
        "eligible": ok,
        "eligibility": ok,
        "decision_status": "ACTIONABLE" if ok else "BLOCKED",
        "score": score,
        "capital_required": capital,
    }


def _shares(score=60.0, capital=5000.0, ok=True):
    return {
        "eligible": ok,
        "eligibility": ok,
        "decision_status": "ACTIONABLE" if ok else "BLOCKED",
        "score": score,
        "capital_required": capital,
    }


def test_csp_preferred_when_higher_score():
    r = arbitrate_csp_vs_shares(_csp(80), _shares(50), {"available_cash": 50000})
    assert r.winner == "CSP"
    assert r.loser == "SHARES"
    assert CSP_PREFERRED in r.reason_codes


def test_shares_preferred_when_higher_score():
    r = arbitrate_csp_vs_shares(_csp(40), _shares(90), {"available_cash": 50000})
    assert r.winner == "SHARES"
    assert SHARES_PREFERRED in r.reason_codes


def test_both_unattractive_stay_cash():
    r = arbitrate_csp_vs_shares(_csp(ok=False), _shares(ok=False), {"available_cash": 50000})
    assert r.winner == "CASH"
    assert BOTH_UNATTRACTIVE in r.reason_codes


def test_cash_insufficient():
    r = arbitrate_csp_vs_shares(_csp(capital=20000), _shares(ok=False), {"available_cash": 1000})
    assert r.winner == "CASH"
    assert CASH_INSUFFICIENT in r.reason_codes


def test_assignment_inappropriate_blocks_csp():
    r = arbitrate_csp_vs_shares(_csp(), _shares(ok=False), {"available_cash": 50000}, ownable=False)
    assert r.winner == "CASH"
    assert ASSIGNMENT_INAPPROPRIATE in r.reason_codes


def test_tie_prefers_csp_deterministically():
    r = arbitrate_csp_vs_shares(_csp(60), _shares(60), {"available_cash": 50000})
    assert r.winner == "CSP"
    assert CSP_PREFERRED in r.reason_codes
