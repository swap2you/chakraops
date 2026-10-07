# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R67 event intelligence — structured placeholders with provenance (no invented live news)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class StructuredEvent:
    event_type: str
    label: str
    event_date: Optional[str] = None
    symbol: Optional[str] = None
    provenance: str = "placeholder"
    source: str = "unconfigured"
    confidence: str = "none"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Placeholder catalog — not live feeds. Empty dates mean "template only".
_PLACEHOLDER_MACRO: List[StructuredEvent] = [
    StructuredEvent(
        event_type="FOMC",
        label="FOMC decision (placeholder)",
        provenance="placeholder_template",
        source="macro_calendar_unconfigured",
        confidence="none",
        notes="Inject trusted FOMC dates when a real calendar provider is configured.",
    ),
    StructuredEvent(
        event_type="CPI",
        label="CPI release (placeholder)",
        provenance="placeholder_template",
        source="macro_calendar_unconfigured",
        confidence="none",
        notes="Inject trusted CPI dates when a real calendar provider is configured.",
    ),
    StructuredEvent(
        event_type="EMPLOYMENT",
        label="Employment / jobs report (placeholder)",
        provenance="placeholder_template",
        source="macro_calendar_unconfigured",
        confidence="none",
        notes="Inject trusted employment dates when configured.",
    ),
    StructuredEvent(
        event_type="HOLIDAY",
        label="US market holiday (placeholder)",
        provenance="placeholder_template",
        source="macro_calendar_unconfigured",
        confidence="none",
        notes="Market holiday list is not loaded until a trusted source is wired.",
    ),
]


def list_event_placeholders(*, include_earnings_template: bool = True) -> Dict[str, Any]:
    """Return structured event templates with explicit provenance.

    Empty live calendars are never treated as "all clear".
    """
    events = [e.to_dict() for e in _PLACEHOLDER_MACRO]
    if include_earnings_template:
        events.append(
            StructuredEvent(
                event_type="EARNINGS",
                label="Earnings date (per-symbol placeholder)",
                symbol=None,
                provenance="placeholder_template",
                source="earnings_calendar_unconfigured",
                confidence="none",
                notes="Use ORATS earnings advisory or broker read-only calendar when entitled.",
            ).to_dict()
        )
    return {
        "schema": "event_intelligence_r67",
        "as_of": _utc_now_iso(),
        "live_calendar_configured": False,
        "invent_live_news": False,
        "events": events,
        "status": "PLACEHOLDERS_ONLY",
        "manual_only": True,
        "trade_execution": False,
    }


def gate_symbol_for_events(
    symbol: str,
    *,
    earnings_within_days: Optional[int] = None,
    macro_events_within_days: Optional[int] = None,
    earnings_date: Optional[str] = None,
    trusted_macro_hits: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Event-aware gate for universe admission/eligibility.

    Without trusted dates, returns advisory HOLD with honest provenance —
    does not invent earnings or macro dates.
    """
    sym = (symbol or "").upper().strip()
    reasons: List[Dict[str, Any]] = []
    action = "PASS"

    if earnings_date and earnings_within_days is not None:
        reasons.append(
            {
                "code": "EARNINGS_WINDOW",
                "source": "operator_or_orats",
                "provenance": "trusted_input",
                "earnings_date": earnings_date,
                "within_days": earnings_within_days,
                "explanation": f"{sym} has earnings {earnings_date} inside configured window.",
            }
        )
        action = "HOLD"
    elif earnings_within_days is not None:
        reasons.append(
            {
                "code": "EARNINGS_UNKNOWN",
                "source": "earnings_calendar_unconfigured",
                "provenance": "missing_trusted_date",
                "explanation": (
                    f"Earnings window check requested for {sym} but no trusted earnings date supplied. "
                    "Fail soft to HOLD/advisory — do not assume clear."
                ),
            }
        )
        action = "HOLD"

    macro_hits = list(trusted_macro_hits or [])
    if macro_events_within_days is not None and macro_hits:
        reasons.append(
            {
                "code": "MACRO_WINDOW",
                "source": "macro_calendar",
                "provenance": "trusted_input",
                "events": macro_hits,
                "within_days": macro_events_within_days,
                "explanation": "Trusted macro events fall inside the gate window.",
            }
        )
        action = "HOLD"
    elif macro_events_within_days is not None and not macro_hits:
        reasons.append(
            {
                "code": "MACRO_UNKNOWN",
                "source": "macro_calendar_unconfigured",
                "provenance": "missing_trusted_calendar",
                "explanation": (
                    "Macro event gate requested but calendar is unconfigured. "
                    "Placeholders only — not treated as all-clear."
                ),
            }
        )
        # Soft advisory; do not hard-block solely on missing macro calendar.
        if action == "PASS":
            action = "ADVISORY"

    return {
        "symbol": sym,
        "action": action,
        "reasons": reasons,
        "as_of": _utc_now_iso(),
        "manual_only": True,
        "trade_execution": False,
        "threshold_retune": False,
    }
