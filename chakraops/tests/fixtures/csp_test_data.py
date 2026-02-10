# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Test fixtures for CSP generator tests."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.core.market.stock_models import StockSnapshot
from app.signals.adapters.theta_options_adapter import NormalizedOptionQuote


def create_test_stock_snapshot(
    symbol: str = "AAPL",
    price: float | None = 150.0,
    snapshot_time: datetime | None = None,
) -> StockSnapshot:
    """Create a test stock snapshot."""
    if snapshot_time is None:
        snapshot_time = datetime(2026, 1, 22, 10, 0, 0)
    return StockSnapshot(
        symbol=symbol,
        price=price,
        bid=price - 0.01 if price is not None else None,
        ask=price + 0.01 if price is not None else None,
        volume=1000000,
        avg_stock_volume_20d=2000000.0,
        has_options=True,
        snapshot_time=snapshot_time,
        data_source="THETA",
    )


def create_test_options(
    underlying: str = "AAPL",
    as_of: datetime | None = None,
    expiry1: date | None = None,
    expiry2: date | None = None,
) -> list[NormalizedOptionQuote]:
    """Create test normalized option quotes with 2 expiries and multiple strikes.

    Expiry 1: 2026-02-20 (29 DTE from 2026-01-22)
    Expiry 2: 2026-03-20 (57 DTE from 2026-01-22)

    Strikes for each expiry:
    - 140 (OTM 6.67%)
    - 145 (OTM 3.33%)
    - 150 (ATM)
    - 155 (ITM -3.33%)
    - 160 (ITM -6.67%)
    """
    if as_of is None:
        as_of = datetime(2026, 1, 22, 10, 0, 0)
    if expiry1 is None:
        expiry1 = date(2026, 2, 20)
    if expiry2 is None:
        expiry2 = date(2026, 3, 20)

    options: list[NormalizedOptionQuote] = []

    # Expiry 1: 2026-02-20
    # Strike 140: OTM 6.67%, bid=1.50, ask=1.60, OI=4000, delta=-0.15
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry1,
            strike=Decimal("140.0"),
            right="PUT",
            bid=1.50,
            ask=1.60,
            last=1.55,
            volume=800,
            open_interest=4000,
            delta=-0.15,
            iv=0.30,
            as_of=as_of,
        )
    )

    # Strike 145: OTM 3.33%, bid=2.50, ask=2.60, OI=5000, delta=-0.25
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry1,
            strike=Decimal("145.0"),
            right="PUT",
            bid=2.50,
            ask=2.60,
            last=2.55,
            volume=1000,
            open_interest=5000,
            delta=-0.25,
            iv=0.28,
            as_of=as_of,
        )
    )

    # Strike 150: ATM, bid=3.50, ask=3.70, OI=8000, delta=-0.50
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry1,
            strike=Decimal("150.0"),
            right="PUT",
            bid=3.50,
            ask=3.70,
            last=3.60,
            volume=2000,
            open_interest=8000,
            delta=-0.50,
            iv=0.25,
            as_of=as_of,
        )
    )

    # Strike 155: ITM -3.33%, bid=5.00, ask=5.20, OI=6000, delta=-0.75
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry1,
            strike=Decimal("155.0"),
            right="PUT",
            bid=5.00,
            ask=5.20,
            last=5.10,
            volume=1500,
            open_interest=6000,
            delta=-0.75,
            iv=0.22,
            as_of=as_of,
        )
    )

    # Expiry 2: 2026-03-20
    # Strike 140: OTM 6.67%, bid=3.00, ask=3.20, OI=3000, delta=-0.20
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry2,
            strike=Decimal("140.0"),
            right="PUT",
            bid=3.00,
            ask=3.20,
            last=3.10,
            volume=500,
            open_interest=3000,
            delta=-0.20,
            iv=0.32,
            as_of=as_of,
        )
    )

    # Strike 145: OTM 3.33%, bid=4.00, ask=4.20, OI=4000, delta=-0.30
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry2,
            strike=Decimal("145.0"),
            right="PUT",
            bid=4.00,
            ask=4.20,
            last=4.10,
            volume=600,
            open_interest=4000,
            delta=-0.30,
            iv=0.30,
            as_of=as_of,
        )
    )

    # Strike 150: ATM, bid=5.00, ask=5.30, OI=7000, delta=-0.55
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry2,
            strike=Decimal("150.0"),
            right="PUT",
            bid=5.00,
            ask=5.30,
            last=5.15,
            volume=1200,
            open_interest=7000,
            delta=-0.55,
            iv=0.27,
            as_of=as_of,
        )
    )

    return options


__all__ = ["create_test_stock_snapshot", "create_test_options"]
