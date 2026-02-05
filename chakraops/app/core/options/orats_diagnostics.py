# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS options diagnostics for dashboard and health checks (no trading logic).

Uses ORATS Live Data provider for expirations and chain. Same result shape as
the previous Theta diagnostics so dashboard/runbook can swap without UI changes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional

import pytz

from app.core.market_time import get_market_state

logger = logging.getLogger(__name__)


@dataclass
class OratsDiagnosticResult:
    now_utc: str
    now_et: str
    market_state: str
    is_market_open: bool
    stock_available: bool = False  # Not from ORATS; kept for UI compat
    option_available: bool = False
    index_available: Optional[bool] = None
    theta_expirations_ok: bool = False  # Same key as Theta diag for dashboard
    expirations_count: int = 0
    first_expiration: Optional[str] = None
    theta_chain_ok: bool = False  # Same key as Theta diag for dashboard
    contracts_count: int = 0
    sample_contract: Optional[Dict[str, Any]] = None
    latency_ms_expirations: Optional[float] = None
    latency_ms_chain: Optional[float] = None
    stock_error: Optional[str] = None
    stock_error_type: Optional[str] = None
    index_error: Optional[str] = None
    index_error_type: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None


def _now_utc_and_et() -> tuple[datetime, datetime]:
    utc = pytz.UTC
    et_tz = pytz.timezone("America/New_York")
    now_utc = datetime.now(utc)
    now_et = now_utc.astimezone(et_tz)
    return now_utc, now_et


def run_orats_diagnostic(symbol: str = "SPY") -> Dict[str, Any]:
    """Run ORATS connectivity diagnostic (expirations + chain). Same dict shape as run_theta_diagnostic."""
    from app.core.options.providers.orats_provider import OratsOptionsChainProvider

    now_utc, now_et = _now_utc_and_et()
    market_state = get_market_state(now_et)
    is_open = market_state == "OPEN"

    result = OratsDiagnosticResult(
        now_utc=now_utc.isoformat(),
        now_et=now_et.isoformat(),
        market_state=market_state,
        is_market_open=is_open,
        stock_available=False,
        option_available=False,
        index_available=None,
        theta_expirations_ok=False,
        expirations_count=0,
        first_expiration=None,
        theta_chain_ok=False,
        contracts_count=0,
        sample_contract=None,
        latency_ms_expirations=None,
        latency_ms_chain=None,
        stock_error=None,
        stock_error_type=None,
        index_error=None,
        index_error_type=None,
        error=None,
        error_type=None,
    )

    provider = OratsOptionsChainProvider()
    symbol_upper = symbol.upper()

    # Expirations
    try:
        t0 = time.monotonic()
        expirations = provider.get_expirations(symbol_upper)
        result.latency_ms_expirations = (time.monotonic() - t0) * 1000.0
        if not expirations:
            result.error = "No expirations from ORATS"
            result.error_type = "NO_EXPIRATIONS"
            return asdict(result)
        result.theta_expirations_ok = True
        result.expirations_count = len(expirations)
        result.first_expiration = expirations[0].isoformat()
    except Exception as e:
        result.error = str(e)
        result.error_type = type(e).__name__
        logger.warning("ORATS diagnostic expirations failed for %s: %s", symbol_upper, e)
        return asdict(result)

    # Nearest expiry in range
    today = date.today()
    future_exp = [d for d in expirations if d >= today]
    expiry_date = min(future_exp) if future_exp else expirations[-1]
    exp_str = expiry_date.strftime("%Y-%m-%d")

    # Chain (puts) for sample
    try:
        t0 = time.monotonic()
        puts = provider.get_chain(symbol_upper, expiry_date, "P")
        result.latency_ms_chain = (time.monotonic() - t0) * 1000.0
        result.contracts_count = len(puts)
        if puts:
            result.theta_chain_ok = True
            result.option_available = True
            c = puts[0]
            result.sample_contract = {
                "expiry": exp_str,
                "strike": c.get("strike"),
                "right": "P",
                "bid": c.get("bid"),
                "ask": c.get("ask"),
                "delta": c.get("delta"),
                "iv": c.get("iv"),
                "open_interest": c.get("open_interest"),
            }
        else:
            result.error = "Empty chain from ORATS"
            result.error_type = "EMPTY_CHAIN"
    except Exception as e:
        result.error = str(e)
        result.error_type = type(e).__name__
        logger.warning("ORATS diagnostic chain failed for %s: %s", symbol_upper, e)

    logger.info(
        "ORATS diag symbol=%s option_available=%s exp_ok=%s chain_ok=%s exp_count=%d chain_count=%d",
        symbol_upper,
        result.option_available,
        result.theta_expirations_ok,
        result.theta_chain_ok,
        result.expirations_count,
        result.contracts_count,
    )
    return asdict(result)


__all__ = ["run_orats_diagnostic", "OratsDiagnosticResult"]
