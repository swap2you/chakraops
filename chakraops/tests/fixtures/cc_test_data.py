# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Test fixtures for CC generator tests."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.signals.adapters.theta_options_adapter import NormalizedOptionQuote


def create_test_cc_options(
    underlying: str = "AAPL",
    as_of: datetime | None = None,
    expiry1: date | None = None,
    expiry2: date | None = None,
) -> list[NormalizedOptionQuote]:
    """Create test normalized CALL option quotes with 2 expiries and multiple strikes.

    Expiry 1: 2026-02-20 (29 DTE from 2026-01-22)
    Expiry 2: 2026-03-20 (57 DTE from 2026-01-22)

    Spot price: 150.0
    Strikes for each expiry:
    - 145 (ITM -3.33%, not OTM)
    - 150 (ATM, not OTM)
    - 155 (OTM 3.33%)
    - 160 (OTM 6.67%)
    - 165 (OTM 10.00%)
    """
    if as_of is None:
        as_of = datetime(2026, 1, 22, 10, 0, 0)
    if expiry1 is None:
        expiry1 = date(2026, 2, 20)
    if expiry2 is None:
        expiry2 = date(2026, 3, 20)

    options: list[NormalizedOptionQuote] = []

    # Expiry 1: 2026-02-20
    # Strike 145: ITM (not OTM), bid=5.00, ask=5.20, OI=6000, delta=0.75
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry1,
            strike=Decimal("145.0"),
            right="CALL",
            bid=5.00,
            ask=5.20,
            last=5.10,
            volume=1500,
            open_interest=6000,
            delta=0.75,
            iv=0.22,
            as_of=as_of,
        )
    )

    # Strike 150: ATM (not OTM), bid=3.50, ask=3.70, OI=8000, delta=0.50
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry1,
            strike=Decimal("150.0"),
            right="CALL",
            bid=3.50,
            ask=3.70,
            last=3.60,
            volume=2000,
            open_interest=8000,
            delta=0.50,
            iv=0.25,
            as_of=as_of,
        )
    )

    # Strike 155: OTM 3.33%, bid=2.50, ask=2.60, OI=5000, delta=0.25
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry1,
            strike=Decimal("155.0"),
            right="CALL",
            bid=2.50,
            ask=2.60,
            last=2.55,
            volume=1000,
            open_interest=5000,
            delta=0.25,
            iv=0.28,
            as_of=as_of,
        )
    )

    # Strike 160: OTM 6.67%, bid=1.50, ask=1.60, OI=4000, delta=0.15
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry1,
            strike=Decimal("160.0"),
            right="CALL",
            bid=1.50,
            ask=1.60,
            last=1.55,
            volume=800,
            open_interest=4000,
            delta=0.15,
            iv=0.30,
            as_of=as_of,
        )
    )

    # Strike 165: OTM 10.00%, bid=0.80, ask=0.90, OI=2000, delta=0.08
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry1,
            strike=Decimal("165.0"),
            right="CALL",
            bid=0.80,
            ask=0.90,
            last=0.85,
            volume=400,
            open_interest=2000,
            delta=0.08,
            iv=0.32,
            as_of=as_of,
        )
    )

    # Expiry 2: 2026-03-20
    # Strike 155: OTM 3.33%, bid=4.00, ask=4.20, OI=4000, delta=0.30
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry2,
            strike=Decimal("155.0"),
            right="CALL",
            bid=4.00,
            ask=4.20,
            last=4.10,
            volume=600,
            open_interest=4000,
            delta=0.30,
            iv=0.30,
            as_of=as_of,
        )
    )

    # Strike 160: OTM 6.67%, bid=3.00, ask=3.20, OI=3000, delta=0.20
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry2,
            strike=Decimal("160.0"),
            right="CALL",
            bid=3.00,
            ask=3.20,
            last=3.10,
            volume=500,
            open_interest=3000,
            delta=0.20,
            iv=0.32,
            as_of=as_of,
        )
    )

    # Strike 165: OTM 10.00%, bid=2.00, ask=2.20, OI=2500, delta=0.12
    options.append(
        NormalizedOptionQuote(
            underlying=underlying,
            expiry=expiry2,
            strike=Decimal("165.0"),
            right="CALL",
            bid=2.00,
            ask=2.20,
            last=2.10,
            volume=300,
            open_interest=2500,
            delta=0.12,
            iv=0.34,
            as_of=as_of,
        )
    )

    return options


__all__ = ["create_test_cc_options"]
