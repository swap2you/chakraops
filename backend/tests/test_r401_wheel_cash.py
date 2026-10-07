# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40.1: Wheel V2 cash must not fall back to total_capital."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_total_gt_zero_cash_zero_stays_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.wheel_v2_routes import _portfolio_from_account

    account = SimpleNamespace(account_id="default", total_capital=100000.0)

    monkeypatch.setattr(
        "app.core.accounts.holdings_db.get_account_summary",
        lambda account_id=None: {
            "account_id": account_id or "default",
            "cash": 0.0,
            "buying_power": 50000.0,
            "balances_present": True,
            "balances_updated_at": "2026-08-10T00:00:00Z",
        },
    )
    port = _portfolio_from_account(account)
    assert port["total_capital"] == 100000.0
    assert port["cash"] == 0.0
    assert port["available_cash"] == 0.0
    assert port["buying_power"] == 50000.0
    assert port["available_cash"] != port["total_capital"]


def test_account_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.wheel_v2_routes import _portfolio_from_account

    summaries = {
        "acct_a": {
            "account_id": "acct_a",
            "cash": 1000.0,
            "buying_power": 1000.0,
            "balances_present": True,
            "balances_updated_at": "t",
        },
        "acct_b": {
            "account_id": "acct_b",
            "cash": 0.0,
            "buying_power": 99999.0,
            "balances_present": True,
            "balances_updated_at": "t",
        },
    }

    def _summary(account_id=None):
        aid = (account_id or "default").strip() or "default"
        return summaries[aid]

    monkeypatch.setattr("app.core.accounts.holdings_db.get_account_summary", _summary)

    a = _portfolio_from_account(SimpleNamespace(account_id="acct_a", total_capital=50000.0))
    b = _portfolio_from_account(SimpleNamespace(account_id="acct_b", total_capital=50000.0))
    assert a["available_cash"] == 1000.0
    assert b["available_cash"] == 0.0
    assert b["buying_power"] == 99999.0


def test_missing_balance_marks_untrusted_available_cash(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.wheel_v2_routes import _portfolio_from_account

    monkeypatch.setattr(
        "app.core.accounts.holdings_db.get_account_summary",
        lambda account_id=None: {
            "account_id": "x",
            "cash": None,
            "buying_power": None,
            "balances_present": False,
        },
    )
    port = _portfolio_from_account(SimpleNamespace(account_id="x", total_capital=25000.0))
    assert port["total_capital"] == 25000.0
    assert port["available_cash"] is None
    assert port["balance_trusted"] is False


def test_buying_power_not_used_as_csp_cash(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.decision_engine.wheel_v2.arbitration import _cash

    assert _cash({"available_cash": 0.0, "cash": 0.0, "buying_power": 80000.0, "balance_trusted": True}) == 0.0
    assert _cash({"available_cash": None, "cash": None, "buying_power": 80000.0, "balance_trusted": False}) == 0.0
