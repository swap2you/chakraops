# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 15.0: Mark refresh service — fetch provider-backed option marks, persist via ADJUST events."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.positions.models import Position

logger = logging.getLogger(__name__)

MarkFetcher = Callable[[str, date, float, str], Optional[float]]
"""Signature: (symbol, expiration, strike, option_type) -> mark_price or None."""


def _default_mark_fetcher(symbol: str, expiration: date, strike: float, option_type: str) -> Optional[float]:
    """Fetch mark from chain provider. Precedence: mid from bid/ask, else mid field, else last."""
    try:
        from app.core.options.chain_provider import OptionType
        from app.core.options.orats_chain_provider import get_chain_provider

        provider = get_chain_provider()
        result = provider.get_chain(symbol.upper(), expiration)
        if not result or not result.success or not result.chain or not result.chain.contracts:
            return None
        strike_tol = 1e-6
        ot_upper = (option_type or "PUT").strip().upper()
        if ot_upper not in ("PUT", "CALL"):
            ot_upper = "PUT"
        target_ot = OptionType.PUT if ot_upper == "PUT" else OptionType.CALL
        for c in result.chain.contracts:
            if abs((c.strike or 0) - strike) > strike_tol:
                continue
            if c.option_type != target_ot:
                continue
            if c.mid.is_valid and c.mid.value is not None:
                return float(c.mid.value)
            if c.bid.is_valid and c.ask.is_valid and c.bid.value is not None and c.ask.value is not None:
                return (float(c.bid.value) + float(c.ask.value)) / 2.0
            if c.last.is_valid and c.last.value is not None:
                return float(c.last.value)
            return None
        return None
    except Exception as e:
        logger.warning("[MARKING] Fetch failed for %s %s %s %s: %s", symbol, expiration, strike, option_type, e)
        return None


def refresh_marks(
    positions: List[Position],
    account_id: Optional[str] = None,
    mark_fetcher: Optional[MarkFetcher] = None,
) -> Tuple[int, int, List[str]]:
    """
    For each OPEN position with contract_key or option_symbol:
    - fetch current option mark (mid of bid/ask if available; else last)
    - update position mark_price_per_contract and mark_time_utc
    - append ADJUST event with payload {kind:"MARK_UPDATE", mark_price, mark_time_utc, source}

    Returns (updated_count, skipped_count, errors).
    """
    from app.core.positions import store as pos_store
    from app.core.positions.events_store import append_event

    fetcher = mark_fetcher or _default_mark_fetcher
    updated = 0
    skipped = 0
    errors: List[str] = []

    _exclude_diag = lambda p: (getattr(p, "symbol", "") or "").strip().upper().startswith("DIAG_TEST")

    for p in positions:
        if (p.status or "").upper() not in ("OPEN", "PARTIAL_EXIT"):
            skipped += 1
            continue
        if _exclude_diag(p):
            skipped += 1
            continue
        if not (getattr(p, "contract_key", None) or getattr(p, "option_symbol", None)):
            skipped += 1
            # Do not add to errors: equity or legacy positions without option id; skip without failing refresh.
            continue
        symbol = (p.symbol or "").strip().upper()
        if not symbol:
            skipped += 1
            errors.append(f"{p.position_id}: no symbol")
            continue
        strike = getattr(p, "strike", None)
        if strike is None:
            skipped += 1
            errors.append(f"{p.position_id}: no strike")
            continue
        exp = getattr(p, "expiration", None) or getattr(p, "expiry", None)
        if not exp:
            skipped += 1
            errors.append(f"{p.position_id}: no expiration")
            continue
        try:
            if "T" in str(exp):
                exp_d = datetime.fromisoformat(str(exp).replace("Z", "+00:00")).date()
            else:
                exp_d = datetime.strptime(str(exp).strip()[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            skipped += 1
            errors.append(f"{p.position_id}: invalid expiration {exp}")
            continue
        strat = (p.strategy or "").strip().upper()
        option_type = "PUT" if strat == "CSP" else "CALL" if strat == "CC" else "PUT"
        if strat not in ("CSP", "CC"):
            skipped += 1
            errors.append(f"{p.position_id}: marking only for CSP/CC")
            continue

        mark_price = fetcher(symbol, exp_d, float(strike), option_type)
        if mark_price is None:
            skipped += 1
            errors.append(f"{p.position_id}: no mark available")
            continue

        now = datetime.now(timezone.utc).isoformat()
        pos_store.update_position(
            p.position_id,
            {
                "mark_price_per_contract": mark_price,
                "mark_time_utc": now,
                "updated_at_utc": now,
            },
        )
        try:
            append_event(
                p.position_id,
                "ADJUST",
                {
                    "kind": "MARK_UPDATE",
                    "mark_price": mark_price,
                    "mark_time_utc": now,
                    "source": "ORATS",
                },
                at_utc=now,
            )
        except Exception as ex:
            logger.warning("[MARKING] Failed to append ADJUST event: %s", ex)
        updated += 1

    return updated, skipped, errors
