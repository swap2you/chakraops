# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52 fixture-based FakeBrokerReadProvider for tests (no live MCP)."""

from __future__ import annotations

from typing import Dict, List, Optional

from app.core.broker.models import (
    BrokerAccount,
    BrokerBalances,
    BrokerOrderSummary,
    BrokerSnapshot,
    EquityPosition,
    OptionPosition,
    utc_now_iso,
)
from app.core.broker.provider import BrokerReadProviderBase


class FakeBrokerReadProvider(BrokerReadProviderBase):
    """In-memory provider for unit tests."""

    def __init__(
        self,
        accounts: Optional[List[BrokerAccount]] = None,
        balances: Optional[Dict[str, BrokerBalances]] = None,
        equities: Optional[Dict[str, List[EquityPosition]]] = None,
        options: Optional[Dict[str, List[OptionPosition]]] = None,
        orders: Optional[Dict[str, List[BrokerOrderSummary]]] = None,
        fail_sync: bool = False,
    ) -> None:
        self._accounts = accounts or [
            BrokerAccount(
                alias="acct_individual",
                account_type="individual",
                masked_account_number="****1234",
                display_name="Individual",
            )
        ]
        self._balances = balances or {
            "acct_individual": BrokerBalances(cash=10000.0, buying_power=10000.0, equity=15000.0, market_value=5000.0)
        }
        self._equities = equities or {
            "acct_individual": [EquityPosition(symbol="AAPL", quantity=10, average_cost=150.0)]
        }
        self._options = options or {"acct_individual": []}
        self._orders = orders or {"acct_individual": []}
        self.fail_sync = fail_sync

    def list_accounts(self) -> List[BrokerAccount]:
        return list(self._accounts)

    def get_account_balances(self, account_alias: str) -> BrokerBalances:
        return self._balances.get(account_alias) or BrokerBalances()

    def get_equity_positions(self, account_alias: str) -> List[EquityPosition]:
        return list(self._equities.get(account_alias) or [])

    def get_option_positions(self, account_alias: str) -> List[OptionPosition]:
        return list(self._options.get(account_alias) or [])

    def get_equity_orders(self, account_alias: str) -> Optional[List[BrokerOrderSummary]]:
        return list(self._orders.get(account_alias) or [])

    def sync_snapshot(self, account_alias: str) -> BrokerSnapshot:
        if self.fail_sync:
            return BrokerSnapshot(
                account_alias=account_alias,
                fetched_at=utc_now_iso(),
                freshness="missing",
                completeness="empty",
                errors=["fake_sync_failed"],
                stale=True,
            )
        return BrokerSnapshot(
            account_alias=account_alias,
            fetched_at=utc_now_iso(),
            balances=self.get_account_balances(account_alias),
            equity_positions=self.get_equity_positions(account_alias),
            option_positions=self.get_option_positions(account_alias),
            equity_orders=self.get_equity_orders(account_alias) or [],
            freshness="fresh",
            completeness="complete",
            errors=[],
            stale=False,
            source="fake",
        )
