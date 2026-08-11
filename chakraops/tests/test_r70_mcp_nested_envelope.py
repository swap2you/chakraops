# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Parse Robinhood MCP nested data envelopes (accounts/portfolio/positions)."""

from __future__ import annotations

from app.core.broker.robinhood_mcp_provider import (
    _as_list,
    _balances_from_portfolio,
    _map_accounts,
    _parse_equity_positions,
    _parse_option_positions,
)


def test_map_accounts_unwraps_data_accounts_envelope() -> None:
    payload = {
        "data": {
            "accounts": [
                {
                    "account_number": "111",
                    "brokerage_account_type": "individual",
                    "is_default": True,
                    "agentic_allowed": False,
                    "type": "margin",
                },
                {
                    "account_number": "222",
                    "brokerage_account_type": "ira_roth",
                    "is_default": False,
                    "agentic_allowed": False,
                    "type": "cash",
                },
                {
                    "account_number": "333",
                    "brokerage_account_type": "individual",
                    "nickname": "Agentic",
                    "is_default": False,
                    "agentic_allowed": True,
                    "type": "cash",
                },
            ]
        },
        "guide": "unused",
    }
    accounts, mapping = _map_accounts(payload)
    assert len(accounts) == 3
    assert mapping["acct_individual"] == "111"
    assert mapping["acct_ira_roth"] == "222"
    assert mapping["acct_agentic"] == "333"
    assert all(a.masked_account_number.startswith("*") for a in accounts)


def test_balances_from_nested_portfolio_and_buying_power_object() -> None:
    payload = {
        "data": {
            "total_value": "100.00",
            "equity_value": "40.00",
            "cash": "60.00",
            "options_value": "0",
            "currency": "USD",
            "buying_power": {"buying_power": "120.00", "display_currency": "USD"},
        }
    }
    bal = _balances_from_portfolio(payload)
    assert bal.cash == 60.0
    assert bal.buying_power == 120.0
    assert bal.equity == 100.0 or bal.equity == 40.0
    assert bal.currency == "USD"


def test_parse_positions_unwraps_data_positions() -> None:
    payload = {"data": {"positions": [{"symbol": "NVDA", "quantity": "1.0", "average_buy_price": "10"}]}}
    eqs = _parse_equity_positions(payload)
    assert len(eqs) == 1
    assert eqs[0].symbol == "NVDA"
    assert eqs[0].quantity == 1.0
    opts = _parse_option_positions({"data": {"positions": []}})
    assert opts == []


def test_as_list_nested_data_dict() -> None:
    assert _as_list({"data": {"accounts": [{"a": 1}]}}, ("accounts", "data")) == [{"a": 1}]
