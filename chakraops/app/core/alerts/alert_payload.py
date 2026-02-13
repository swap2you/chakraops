# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.0: Alert payload builder. JSON artifact only; no Slack send.
Payload is 100% derived from existing traces/results; does not change decisions.
STRICT: No secrets (no tokens, no env vars) in payload."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


REQUIRED_TOP_KEYS = frozenset({
    "run_id",
    "ts_utc",
    "symbol",
    "mode_decision",
    "primary_reason_code",
    "rejection_reason_codes",
})


def build_alert_payload(
    symbol: str,
    run_id: str,
    eligibility_trace: Optional[Dict[str, Any]],
    stage2_trace: Optional[Dict[str, Any]],
    candles_meta: Optional[Dict[str, Any]],
    config_meta: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build alert payload dict from existing traces. Never include secrets.
    """
    now = datetime.now(timezone.utc).isoformat()
    el = eligibility_trace or {}
    st2 = stage2_trace or {}
    candles_meta = candles_meta or {}
    config_meta = config_meta or {}

    payload: Dict[str, Any] = {
        "run_id": run_id,
        "ts_utc": now,
        "symbol": (symbol or "").strip().upper(),
        "mode_decision": (el.get("mode_decision") or "NONE").strip().upper(),
        "primary_reason_code": el.get("primary_reason_code"),
        "rejection_reason_codes": el.get("rejection_reason_codes") if isinstance(el.get("rejection_reason_codes"), list) else [],
    }

    # Gating metrics
    payload["regime_daily"] = el.get("regime")
    if "regime_weekly" in el:
        payload["regime_weekly"] = el.get("regime_weekly")
    payload["rsi"] = el.get("rsi14")
    payload["atr_pct"] = el.get("atr_pct")
    payload["support_level"] = el.get("support_level")
    payload["resistance_level"] = el.get("resistance_level")
    payload["distance_to_support_pct"] = el.get("distance_to_support_pct")
    payload["distance_to_resistance_pct"] = el.get("distance_to_resistance_pct")

    # Near support/resistance from rule_checks
    rule_checks = el.get("rule_checks") or []
    for rc in rule_checks:
        name = (rc.get("name") or "").strip()
        if name == "NEAR_SUPPORT":
            payload["near_support_pass"] = rc.get("passed")
        elif name == "NEAR_RESISTANCE":
            payload["near_resistance_pass"] = rc.get("passed")

    # Stage2 summary when mode != NONE
    mode = payload["mode_decision"]
    if mode in ("CSP", "CC"):
        sel = st2.get("selected_trade")
        if isinstance(sel, dict):
            payload["stage2_summary"] = {
                "selected_type": "PUT" if mode == "CSP" else "CALL",
                "expiration": sel.get("exp"),
                "strike": sel.get("strike"),
                "delta": sel.get("abs_delta"),
                "bid": sel.get("bid"),
                "ask": sel.get("ask"),
                "volume": sel.get("volume"),
                "open_interest": sel.get("oi"),
                "spread_pct": sel.get("spread_pct"),
            }
        else:
            payload["stage2_summary"] = None
    else:
        payload["stage2_summary"] = None

    # data_as_of
    payload["data_as_of"] = {
        "candles_as_of": candles_meta.get("last_date") or candles_meta.get("last_ts"),
        "chain_as_of": st2.get("chain_as_of") or st2.get("fetched_at"),
    }

    return payload
