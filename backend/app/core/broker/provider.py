# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52 BrokerReadProvider protocol — typed read surface only (no write methods)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, runtime_checkable

from app.core.broker.models import (
    BrokerAccount,
    BrokerBalances,
    BrokerOrderSummary,
    BrokerSnapshot,
    EquityPosition,
    OptionPosition,
)


@runtime_checkable
class BrokerReadProvider(Protocol):
    """Typed read-only broker provider. No place/cancel/exercise methods."""

    def list_accounts(self) -> List[BrokerAccount]:
        ...

    def get_account_balances(self, account_alias: str) -> BrokerBalances:
        ...

    def get_equity_positions(self, account_alias: str) -> List[EquityPosition]:
        ...

    def get_option_positions(self, account_alias: str) -> List[OptionPosition]:
        ...

    def get_equity_orders(self, account_alias: str) -> Optional[List[BrokerOrderSummary]]:
        ...

    def sync_snapshot(self, account_alias: str) -> BrokerSnapshot:
        ...


class BrokerReadProviderBase(ABC):
    """ABC companion for concrete providers / fakes."""

    @abstractmethod
    def list_accounts(self) -> List[BrokerAccount]:
        raise NotImplementedError

    @abstractmethod
    def get_account_balances(self, account_alias: str) -> BrokerBalances:
        raise NotImplementedError

    @abstractmethod
    def get_equity_positions(self, account_alias: str) -> List[EquityPosition]:
        raise NotImplementedError

    @abstractmethod
    def get_option_positions(self, account_alias: str) -> List[OptionPosition]:
        raise NotImplementedError

    def get_equity_orders(self, account_alias: str) -> Optional[List[BrokerOrderSummary]]:
        return None

    @abstractmethod
    def sync_snapshot(self, account_alias: str) -> BrokerSnapshot:
        raise NotImplementedError
