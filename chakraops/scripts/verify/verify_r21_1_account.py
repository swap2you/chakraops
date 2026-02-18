#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R21.1 verification: assert account summary and holdings API shape via holdings_db (no server).
Runs against default DB (out/account.db). Sets balances to 1000/900 and adds then removes holding R21_VERIFY."""

from __future__ import annotations

import sys
from pathlib import Path

# Run from chakraops/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.accounts.holdings_db import (
    init_db,
    get_account_summary,
    list_holdings,
    set_balances,
    upsert_holding,
    delete_holding,
    get_holdings_for_evaluation,
)


def main() -> int:
    init_db()
    summary = get_account_summary()
    assert "account_id" in summary, summary
    assert "cash" in summary, summary
    assert "buying_power" in summary, summary
    assert "holdings_count" in summary, summary
    assert summary["account_id"] == "default", summary

    holdings = list_holdings()
    assert isinstance(holdings, list), type(holdings)
    for h in holdings:
        assert "symbol" in h and "shares" in h and "updated_at" in h, h

    set_balances(1000.0, 900.0)
    summary2 = get_account_summary()
    assert summary2["cash"] == 1000.0, summary2
    assert summary2["buying_power"] == 900.0, summary2

    upsert_holding("R21_VERIFY", 100, 50.0)
    ev = get_holdings_for_evaluation()
    assert "R21_VERIFY" in ev, ev
    assert ev["R21_VERIFY"] == 100, ev

    delete_holding("R21_VERIFY")
    ev2 = get_holdings_for_evaluation()
    assert "R21_VERIFY" not in ev2, ev2

    print("R21.1 account verification OK: summary, holdings, balances, get_holdings_for_evaluation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
