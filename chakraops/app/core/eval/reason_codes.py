# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Map internal reason codes to plain-English for UI. Additive: keep codes for debug."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _fmt(msg: str, **kwargs: Any) -> str:
    for k, v in kwargs.items():
        msg = msg.replace("{" + k + "}", str(v) if v is not None else "—")
    return msg


def format_reason_for_display(raw_reason: str | None) -> str:
    """Convert raw gate/reason string to English; never show rejected_due_to_delta=N as delta value."""
    if not raw_reason or not isinstance(raw_reason, str):
        return ""
    r = raw_reason.strip()
    m = re.search(r"rejected_due_to_delta\s*=\s*(\d+)", r, re.I)
    if m:
        return f"Rejected due to delta band (rejected_count={m.group(1)})."
    for code, msg in [
        ("FAIL_RSI_RANGE", "RSI outside preferred range"),
        ("FAIL_RSL_CC", "RSL / CC rejected"),
        ("FAIL_NOT_NEAR_SUPPORT", "Not near support"),
        ("FAIL_NO_HOLDINGS", "No shares held; covered calls disabled"),
        ("DATA_INCOMPLETE", "Required data missing"),
        ("FAIL_REGIME", "Regime conflict"),
    ]:
        if code in r:
            return msg
    return r if len(r) < 80 else r[:77] + "..."


def _parse_primary_to_safe_message(primary: str) -> str:
    """Convert raw primary_reason to safe English; never emit rejected_due_to_delta=N as delta value."""
    import re
    m = re.search(r"rejected_due_to_delta\s*=\s*(\d+)", primary, re.I)
    if m:
        n = m.group(1)
        return f"Rejected due to delta band (rejected_count={n})."
    return "See diagnostics for details."


def explain_reasons(
    primary_reason: str | None,
    symbol_eligibility: Dict[str, Any] | None,
    contract_eligibility: Dict[str, Any] | None,
    top_rejection_reasons: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    """
    Build reasons_explained from raw codes. Returns list of { code, severity, title, message, metrics }.
    """
    out: List[Dict[str, Any]] = []
    primary = (primary_reason or "").strip()

    # Delta rejection: gate uses abs(delta) vs band; message must match (abs(delta) and value used by gate).
    if "rejected_due_to_delta" in primary or (top_rejection_reasons and top_rejection_reasons.get("sample_rejected_due_to_delta")):
        samples = (top_rejection_reasons or {}).get("sample_rejected_due_to_delta") or []
        if samples:
            s0 = samples[0]
            obs_abs = s0.get("observed_delta_decimal_abs")
            obs_pct_abs = s0.get("observed_delta_pct_abs")
            target = s0.get("target_range_decimal", "0.20–0.40")
            if obs_abs is not None:
                pct_val = obs_pct_abs if obs_pct_abs is not None else round(float(obs_abs) * 100, 0)
                msg = f"abs(delta) {float(obs_abs):.2f} ({pct_val:.0f}%) outside target range {target}."
            else:
                obs_dec = s0.get("observed_delta_decimal") or s0.get("observed_delta_decimal_raw")
                obs_pct = s0.get("observed_delta_pct") or obs_pct_abs
                msg = f"abs(delta) {obs_dec} ({(str(obs_pct) + '%') if obs_pct is not None else '—'}) outside target range {target}."
            out.append({
                "code": "rejected_due_to_delta",
                "severity": "FAIL",
                "title": "Delta outside target range",
                "message": msg,
                "metrics": {"observed_delta_decimal_abs": obs_abs, "observed_delta_pct_abs": obs_pct_abs, "target_range_decimal": target},
            })
        else:
            # No sample: primary may be "rejected_due_to_delta=N" where N is rejection count; include count in message.
            import re as _re
            _m = _re.search(r"rejected_due_to_delta\s*=\s*(\d+)", primary, _re.I)
            count_str = f" (rejected_count={_m.group(1)})" if _m else ""
            out.append({
                "code": "rejected_due_to_delta",
                "severity": "FAIL",
                "title": "Delta outside target range",
                "message": f"No put contracts in delta band (abs(delta) 0.20–0.40){count_str}. See diagnostics for details.",
                "metrics": {"target_range_decimal": "0.20–0.40"},
            })

    # DATA_INCOMPLETE
    if "DATA_INCOMPLETE" in primary or "required missing" in primary.lower():
        sel = symbol_eligibility or {}
        missing = sel.get("required_data_missing") or []
        msg = f"Required data missing: {', '.join(missing)}." if missing else primary or "Required data missing."
        out.append({
            "code": "DATA_INCOMPLETE",
            "severity": "FAIL",
            "title": "Data incomplete",
            "message": msg,
            "metrics": {"required_data_missing": missing},
        })

    # RSI / support / liquidity patterns (generic code mapping)
    if "FAIL_RSI" in primary or "RSI" in primary.upper():
        m = re.search(r"RSI\s*([\d.]+).*?([\d.]+)\s*[-–]\s*([\d.]+)", primary, re.I)
        if m:
            rsi, lo, hi = m.group(1), m.group(2), m.group(3)
            msg = f"RSI {rsi} not in required range {lo}–{hi}."
        else:
            msg = "RSI outside preferred range."
        out.append({"code": "FAIL_RSI_RANGE", "severity": "FAIL", "title": "RSI outside preferred range", "message": msg, "metrics": {}})
    if "NOT_NEAR_SUPPORT" in primary or ("support" in primary.lower() and "distance" in primary.lower()):
        m = re.search(r"distance\s*([\d.]+)%\s*>\s*tolerance\s*([\d.]+)%", primary, re.I)
        if m:
            msg = f"Not near support: distance {m.group(1)}% > tolerance {m.group(2)}%."
        else:
            msg = "Not near support."
        out.append({"code": "FAIL_NOT_NEAR_SUPPORT", "severity": "FAIL", "title": "Not near support", "message": msg, "metrics": {}})
    if "NO_HOLDINGS" in primary or "no shares" in primary.lower():
        out.append({"code": "FAIL_NO_HOLDINGS", "severity": "FAIL", "title": "No shares held", "message": "No shares held; covered calls disabled.", "metrics": {}})

    # Contract selection / liquidity — never emit raw primary; use generic or skip if delta already explained
    if ("No contract passed" in primary or "No suitable contract" in primary) and not any(r.get("code") == "rejected_due_to_delta" for r in out):
        out.append({
            "code": "CONTRACT_SELECTION_FAIL",
            "severity": "FAIL",
            "title": "No contract passed filters",
            "message": "No contracts passed option liquidity and delta filters.",
            "metrics": {},
        })

    # FAIL_RSL_CC and other common codes
    if "FAIL_RSL_CC" in primary or "FAIL_RSL" in primary:
        out.append({"code": "FAIL_RSL_CC", "severity": "FAIL", "title": "RSL / CC", "message": "Rejected (RSL / CC).", "metrics": {}})
    if "FAIL_REGIME" in primary or "FAIL_REGIME_CONFLICT" in primary:
        out.append({"code": "FAIL_REGIME", "severity": "FAIL", "title": "Regime conflict", "message": "Regime conflict.", "metrics": {}})

    # If nothing matched, parse primary to avoid raw codes (e.g. rejected_due_to_delta=32 → rejected_count)
    if not out and primary:
        msg = _parse_primary_to_safe_message(primary)
        out.append({
            "code": "OTHER",
            "severity": "WARN",
            "title": "Reason",
            "message": msg,
            "metrics": {},
        })
    return out[:10]
