# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.2: Slack alert dispatcher. Deterministic, deduplicated. No trading logic."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

ENV_WEBHOOK_CRITICAL = "SLACK_WEBHOOK_CRITICAL"
ENV_WEBHOOK_SIGNALS = "SLACK_WEBHOOK_SIGNALS"
ENV_WEBHOOK_HEALTH = "SLACK_WEBHOOK_HEALTH"
ENV_WEBHOOK_DAILY = "SLACK_WEBHOOK_DAILY"

DEFAULT_STATE_PATH = "artifacts/alerts/last_sent_state.json"
# R24.1: Actionable dedupe state (chakraops/data to avoid new out/ artifacts)
def _default_actionable_state_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "slack_actionable_dedupe.json"

# R24.0/R24.1: Slack messages must never contain these (no raw codes, no secrets, no paths/tracebacks)
FORBIDDEN_IN_SLACK = ("FAIL_", "WARN_", "api_key", "token", "traceback", "Traceback", "File \"")
CRITICAL_ALERT_TYPES = frozenset({"CRITICAL", "POSITION_EXIT", "STOP", "INVALIDATION"})
ALERT_THROTTLE_MINUTES = 15  # Same alert type + symbol at most once per N minutes (critical exempt)
# R24.1: Actionable dedupe — same (symbol, strategy, action, contract, size) within N minutes unless severity changes
ACTIONABLE_DEDUPE_MINUTES = int(os.getenv("SLACK_ACTIONABLE_DEDUPE_MINUTES", "15"))


def is_slack_configured() -> bool:
    """True if any Phase 7.2 webhook is set. Does not require all four."""
    return any(
        (os.getenv(k) or "").strip()
        for k in (
            ENV_WEBHOOK_CRITICAL,
            ENV_WEBHOOK_SIGNALS,
            ENV_WEBHOOK_HEALTH,
            ENV_WEBHOOK_DAILY,
        )
    )


def get_slack_config_status() -> Dict[str, bool]:
    """Per-webhook status for startup log: {name: configured}."""
    return {
        "CRITICAL": bool((os.getenv(ENV_WEBHOOK_CRITICAL) or "").strip()),
        "SIGNALS": bool((os.getenv(ENV_WEBHOOK_SIGNALS) or "").strip()),
        "HEALTH": bool((os.getenv(ENV_WEBHOOK_HEALTH) or "").strip()),
        "DAILY": bool((os.getenv(ENV_WEBHOOK_DAILY) or "").strip()),
    }


def get_test_webhook_url() -> Optional[str]:
    """First available webhook URL for generic test send (e.g. UI Test Slack). Prefer SIGNALS."""
    for key in (ENV_WEBHOOK_SIGNALS, ENV_WEBHOOK_CRITICAL, ENV_WEBHOOK_HEALTH, ENV_WEBHOOK_DAILY):
        url = (os.getenv(key) or "").strip()
        if url:
            return url
    return (os.getenv("SLACK_WEBHOOK_URL") or "").strip() or None


# R21.5.1: Channel names for 4 webhooks (signals, daily, data_health, critical)
def get_webhook_for_channel(channel: str) -> Optional[str]:
    """
    Return webhook URL for channel: signals | daily | data_health | critical.
    Backwards compat: SLACK_WEBHOOK_URL is treated as signals default when channel=signals.
    """
    c = (channel or "").strip().lower()
    if c == "signals":
        return (os.getenv(ENV_WEBHOOK_SIGNALS) or "").strip() or (os.getenv("SLACK_WEBHOOK_URL") or "").strip() or None
    if c == "daily":
        return (os.getenv(ENV_WEBHOOK_DAILY) or "").strip() or None
    if c == "data_health":
        return (os.getenv(ENV_WEBHOOK_HEALTH) or "").strip() or None
    if c == "critical":
        return (os.getenv(ENV_WEBHOOK_CRITICAL) or "").strip() or None
    return None


def _get_webhook(event_type: str) -> Optional[str]:
    """Return webhook URL for event_type. None if not set (do not crash)."""
    t = (event_type or "").strip().upper()
    if t == "CRITICAL":
        return os.environ.get(ENV_WEBHOOK_CRITICAL) or None
    if t == "SIGNAL":
        return os.environ.get(ENV_WEBHOOK_SIGNALS) or None
    if t == "HEALTH":
        return os.environ.get(ENV_WEBHOOK_HEALTH) or None
    if t == "DAILY":
        return os.environ.get(ENV_WEBHOOK_DAILY) or None
    return None


def _get_webhook_for_position(exit_priority: Optional[str]) -> Optional[str]:
    """Phase 7.3: Route POSITION alert by exit_priority. PANIC/EXPIRY_CRITICAL/NORMAL_EXIT -> CRITICAL; FAST_CAPTURE/ADVISORY -> SIGNALS."""
    p = (exit_priority or "").strip().upper()
    if p in ("PANIC", "EXPIRY_CRITICAL", "NORMAL_EXIT"):
        return os.environ.get(ENV_WEBHOOK_CRITICAL) or None
    if p in ("FAST_CAPTURE", "ADVISORY"):
        return os.environ.get(ENV_WEBHOOK_SIGNALS) or None
    return os.environ.get(ENV_WEBHOOK_SIGNALS) or None  # NONE/unknown -> SIGNALS


def _state_hash(payload: Dict[str, Any]) -> str:
    """Deterministic hash for dedup. No secrets in payload."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_state(state_path: Union[str, Path]) -> Dict[str, Any]:
    path = Path(state_path)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: Dict[str, Any], state_path: Union[str, Path]) -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def should_send_alert(
    event_key: str,
    new_state_hash: str,
    state_path: Union[str, Path] = DEFAULT_STATE_PATH,
) -> bool:
    """
    If stored hash equals new_state_hash → return False (suppress).
    Else update stored state and return True (allow send).
    """
    state = _load_state(state_path)
    old_hash = state.get(event_key)
    if old_hash == new_state_hash:
        return False
    state[event_key] = new_state_hash
    _save_state(state, state_path)
    return True


try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]


def send_slack_message(webhook_url: str, text: str) -> bool:
    """POST JSON {text: message} to webhook. Return True on success. Handle exceptions safely."""
    if not webhook_url or not text:
        return False
    if _requests is None:
        logger.warning("[Slack] requests not installed, skip send")
        return False
    try:
        r = _requests.post(
            webhook_url,
            json={"text": text},
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        ok = 200 <= r.status_code < 300
        if not ok:
            logger.warning("[Slack] webhook returned %s: %s", r.status_code, r.text[:200])
        return ok
    except Exception as e:
        logger.warning("[Slack] send failed: %s", e)
        return False


def _fmt_signal(p: Dict[str, Any]) -> str:
    """Phase 7.3: Structured SIGNAL format. Phase 8.2: Guardrail Adjusted line when applicable."""
    lines = [
        "🟢 *TRADE SIGNAL*",
        "Symbol: %s" % (p.get("symbol") or "?"),
        "Mode: %s" % (p.get("mode") or p.get("mode_decision") or "?"),
        "Tier: %s" % (p.get("tier") or "?"),
        "Severity: %s" % (p.get("severity") or "?"),
        "Score: %s" % (_str_num(p.get("composite_score"))),
        "",
        "Strike: %s" % (_str_num(p.get("strike"))),
        "DTE: %s" % (_str_num(p.get("dte"))),
        "Delta: %s" % (_str_num(p.get("delta"))),
        "Capital Required: %s" % (_str_capital(p.get("capital_required_estimate"))),
    ]
    # Phase 8.2: Guardrail Adjusted X → Y when contracts were reduced
    guardrail_msg = p.get("guardrail_adjusted_msg")
    if guardrail_msg:
        lines.append("")
        lines.append("*%s*" % guardrail_msg)
    lines.extend([
        "",
        "Exit Plan:",
        "  Base Target: %s" % (_str_pct(p.get("exit_base_target_pct"))),
        "  Extension: %s" % (_str_pct(p.get("exit_extension_target_pct"))),
        "  T1: %s" % (_str_num(p.get("exit_T1"))),
        "  T2: %s" % (_str_num(p.get("exit_T2"))),
    ])
    return "\n".join(lines)


def _fmt_position_exit(p: Dict[str, Any], exit_priority: Optional[str] = None) -> str:
    """Phase 7.3: CRITICAL EXIT / POSITION EXIT REQUIRED format."""
    priority = (exit_priority or p.get("exit_priority") or "?").strip()
    pct = p.get("premium_capture_pct")
    pct_s = "%.0f%%" % (pct * 100) if pct is not None else "N/A"
    lines = [
        "🔴 *POSITION EXIT REQUIRED*",
        "Symbol: %s" % (p.get("symbol") or "?"),
        "Mode: %s" % (p.get("mode") or "?"),
        "Premium Capture: %s" % pct_s,
        "DTE: %s" % (_str_num(p.get("dte"))),
        "",
        "Reason: %s" % priority,
        "Action: CLOSE POSITION IMMEDIATELY",
    ]
    return "\n".join(lines)


def _fmt_health(p: Dict[str, Any]) -> str:
    """Phase 7.3: SYSTEM HEALTH ISSUE format."""
    failed = p.get("failed_symbols") or p.get("failed")
    if isinstance(failed, list):
        failed_s = str(failed)
    else:
        failed_s = str(failed) if failed is not None else "?"
    ts = p.get("timestamp") or p.get("ts_utc") or ""
    lines = [
        "⚠️ *SYSTEM HEALTH ISSUE*",
        "Component: HEALTH_GATE",
        "Status: FAIL",
        "Failed Symbols: %s" % failed_s,
        "Timestamp: %s" % (ts if ts else "N/A"),
    ]
    return "\n".join(lines)


def _fmt_daily(p: Dict[str, Any]) -> str:
    """Phase 7.3: DAILY SUMMARY format."""
    lines = ["📊 *DAILY SUMMARY*", ""]
    top_signals = p.get("top_signals") or []
    if top_signals:
        lines.append("Top Signals:")
        for i, s in enumerate(top_signals[:5], 1):
            sym = s.get("symbol") if isinstance(s, dict) else str(s)
            tier = s.get("tier") if isinstance(s, dict) else "?"
            sev = s.get("severity") if isinstance(s, dict) else "?"
            lines.append("%s. %s (Tier %s, %s)" % (i, sym, tier, sev))
        lines.append("")
    lines.append("Open Positions: %s" % (p.get("open_positions_count") or 0))
    lines.append("Total Capital Used: %s" % (_str_capital(p.get("total_capital_used"))))
    exp = p.get("exposure_pct")
    lines.append("Portfolio Exposure: %s" % ("%.1f%%" % exp if exp is not None else "N/A"))
    lines.append("")
    avg_cap = p.get("average_premium_capture")
    lines.append("Average Premium Capture: %s" % ("%.0f%%" % (avg_cap * 100) if avg_cap is not None else "N/A"))
    lines.append("Exit Alerts Today: %s" % (p.get("exit_alerts_today") or p.get("alerts_count") or 0))
    # Phase 8.5: Portfolio Risk Summary section
    prs = p.get("portfolio_risk_summary")
    if prs and isinstance(prs, dict):
        lines.append("")
        lines.append("*%s*" % (prs.get("title") or "Portfolio Risk Summary"))
        for ln in prs.get("lines") or []:
            lines.append(ln)
    return "\n".join(lines)


def _str_num(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return str(float(v))
    except (TypeError, ValueError):
        return str(v)


def _str_pct(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return "%.0f%%" % (float(v) * 100)
    except (TypeError, ValueError):
        return str(v)


def _str_capital(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return "$%s" % (int(float(v)))
    except (TypeError, ValueError):
        return str(v)


def _sanitize_slack_text(text: str) -> str:
    """R24.0: Remove any forbidden substrings from Slack message (no FAIL_/WARN_/secrets)."""
    if not text:
        return text
    out = text
    for forbidden in FORBIDDEN_IN_SLACK:
        out = out.replace(forbidden, "")
    return out


def build_actionable_message_r240(payload: Dict[str, Any]) -> str:
    """
    R24.0: Per-symbol actionable Slack message. Includes contract identity, delta, bid/ask,
    credit estimate, suggested contracts, required cash, top 2 reasons (safe labels only).
    Never includes FAIL_/WARN_ or secrets.
    """
    lines = [
        "*Actionable: %s*" % (payload.get("symbol") or "?"),
        "Strategy: %s" % (payload.get("strategy") or payload.get("mode") or "?"),
    ]
    if payload.get("expiry") or payload.get("expiration"):
        lines.append("Expiry: %s" % (payload.get("expiry") or payload.get("expiration")))
    if payload.get("strike") is not None:
        lines.append("Strike: %s" % payload.get("strike"))
    if payload.get("delta") is not None:
        lines.append("Delta: %s" % payload.get("delta"))
    bid, ask = payload.get("bid"), payload.get("ask")
    if bid is not None or ask is not None:
        lines.append("Bid/Ask: %s / %s" % (_str_num(bid), _str_num(ask)))
    if payload.get("credit_estimate") is not None:
        lines.append("Credit estimate: %s" % _str_capital(payload.get("credit_estimate")))
    if payload.get("suggested_contracts") is not None:
        lines.append("Suggested contracts: %s" % payload.get("suggested_contracts"))
    if payload.get("required_cash") is not None:
        lines.append("Required cash: %s" % _str_capital(payload.get("required_cash")))
    reasons = payload.get("reasons_safe") or payload.get("top_reasons") or []
    if isinstance(reasons, list) and reasons:
        for r in reasons[:2]:
            if isinstance(r, str) and r and not any(f in r for f in FORBIDDEN_IN_SLACK):
                lines.append("• %s" % r)
    raw = "\n".join(lines)
    return _sanitize_slack_text(raw)


def build_actionable_message_r241(payload: Dict[str, Any]) -> str:
    """
    R24.1/R24.2: Per-symbol Action block using next_action_details. OPTIONS: strategy, expiry, strike,
    next_action, rationale, sizing, key levels (spot, T1, stop), contract_key/option_symbol, delta_best, DTE,
    bid/ask/spread_pct. SHARES: next_action, rationale, spot, entry zone, stop, T1, suggested
    shares/cost, risk %. All copy safe/plain-English; no FAIL_/WARN_/paths.
    """
    lines = [
        "*Action: %s*" % (payload.get("symbol") or "?"),
        "Strategy: %s" % (payload.get("strategy") or payload.get("mode") or "?"),
        "Next action: %s" % (payload.get("next_action_code") or payload.get("action") or "NONE"),
    ]
    if payload.get("expiry") or payload.get("expiration"):
        lines.append("Expiry: %s" % (payload.get("expiry") or payload.get("expiration")))
    if payload.get("strike") is not None:
        lines.append("Strike: %s" % _str_num(payload.get("strike")))
    rationale = payload.get("rationale_lines") or payload.get("rationale") or []
    if isinstance(rationale, list):
        for r in rationale[:2]:
            if isinstance(r, str) and r and not any(f in r for f in FORBIDDEN_IN_SLACK):
                lines.append("• %s" % r)
    elif isinstance(rationale, str) and rationale and not any(f in rationale for f in FORBIDDEN_IN_SLACK):
        lines.append("• %s" % rationale)
    details = payload.get("next_action_details") or {}
    key_num = details.get("key_numbers") or payload.get("key_numbers") or {}
    if key_num.get("spot") is not None:
        lines.append("Spot: %s" % _str_num(key_num.get("spot")))
    if key_num.get("t1") is not None:
        lines.append("T1: %s" % _str_num(key_num.get("t1")))
    if key_num.get("delta_best") is not None:
        lines.append("Delta: %s" % _str_num(key_num.get("delta_best")))
    if key_num.get("dte") is not None:
        lines.append("DTE: %s" % _str_num(key_num.get("dte")))
    strategy = (payload.get("strategy") or payload.get("mode") or "").upper()
    if strategy in ("CSP", "CC", "OPTIONS"):
        if payload.get("contract_key"):
            lines.append("Contract: %s" % (payload.get("contract_key") or ""))
        if payload.get("option_symbol"):
            lines.append("Option: %s" % (payload.get("option_symbol") or ""))
        bid, ask = payload.get("bid"), payload.get("ask")
        if bid is not None or ask is not None:
            lines.append("Bid/Ask: %s / %s" % (_str_num(bid), _str_num(ask)))
        spread = payload.get("spread_pct")
        if spread is not None:
            lines.append("Spread: %s" % (_str_num(spread) + "%"))
        if payload.get("suggested_contracts") is not None:
            lines.append("Suggested contracts: %s" % payload.get("suggested_contracts"))
        if payload.get("required_cash") is not None:
            lines.append("Required cash: %s" % _str_capital(payload.get("required_cash")))
        if key_num.get("premium_est") is not None:
            lines.append("Credit est: %s" % _str_capital(key_num.get("premium_est")))
    else:
        entry = payload.get("entry_zone") or key_num.get("entry_zone")
        if isinstance(entry, dict) and entry.get("low") is not None and entry.get("high") is not None:
            lines.append("Entry zone: %s – %s" % (_str_num(entry.get("low")), _str_num(entry.get("high"))))
        elif key_num.get("stop") is not None:
            lines.append("Stop: %s" % _str_num(key_num.get("stop")))
        if payload.get("suggested_shares") is not None:
            lines.append("Suggested shares: %s" % payload.get("suggested_shares"))
        if payload.get("suggested_cost") is not None:
            lines.append("Est cost: %s" % _str_capital(payload.get("suggested_cost")))
        if payload.get("risk_pct_used") is not None:
            lines.append("Risk %%: %s" % _str_pct(payload.get("risk_pct_used")))
    raw = "\n".join(lines)
    return _sanitize_slack_text(raw)


def _actionable_dedupe_key(
    symbol: str,
    strategy: str,
    action: str,
    contract_key: Optional[str],
    size: Optional[str],
) -> str:
    """R24.1: Deterministic key for actionable dedupe (symbol, strategy, action, contract, size)."""
    c = (contract_key or "").strip() or "_"
    s = (size or "").strip() or "_"
    return "actionable|%s|%s|%s|%s|%s" % (
        (symbol or "").strip().upper(),
        (strategy or "").strip().upper(),
        (action or "").strip().upper(),
        c,
        s,
    )


def should_send_actionable_message(
    symbol: str,
    strategy: str,
    action: str,
    contract_key: Optional[str],
    size: Optional[str],
    severity: str = "normal",
    state_path: Union[str, Path, None] = None,
    throttle_minutes: Optional[int] = None,
) -> bool:
    """
    R24.1: Dedupe actionable Slack: do not resend same (symbol, strategy, action, contract, size)
    within throttle_minutes unless severity changed. Returns True if send allowed, False to suppress.
    Uses chakraops/data/slack_actionable_dedupe.json by default.
    """
    if state_path is None:
        state_path = _default_actionable_state_path()
    if throttle_minutes is None:
        throttle_minutes = ACTIONABLE_DEDUPE_MINUTES
    key = _actionable_dedupe_key(symbol, strategy, action, contract_key, size)
    state = _load_state(state_path)
    entry = state.get(key)
    if isinstance(entry, dict):
        ts = entry.get("ts") or 0
        sev = entry.get("severity") or "normal"
        import time
        now = time.time()
        if (now - ts) < throttle_minutes * 60.0 and sev == severity:
            return False
    elif isinstance(entry, str):
        import time
        now = time.time()
        if (now - float(entry or 0)) < throttle_minutes * 60.0:
            return False
    import time
    state[key] = {"ts": time.time(), "severity": severity}
    _save_state(state, state_path)
    return True


def _format_message(event_type: str, payload: Dict[str, Any], exit_priority_fire: Optional[str] = None) -> str:
    """Phase 7.3: Structured Slack messages. No raw JSON, no secrets. R24.0: sanitized."""
    t = (event_type or "").strip().upper()
    if t == "SIGNAL":
        return _fmt_signal(payload)
    if t == "CRITICAL":
        return _sanitize_slack_text(_fmt_position_exit(payload, exit_priority_fire))
    if t == "POSITION":
        return _sanitize_slack_text(_fmt_position_exit(payload, payload.get("exit_priority") or exit_priority_fire))
    if t == "HEALTH":
        return _sanitize_slack_text(_fmt_health(payload))
    if t == "DAILY":
        return _sanitize_slack_text(_fmt_daily(payload))
    raw = "*Alert* %s" % t
    return _sanitize_slack_text(raw)


def route_alert(
    event_type: str,
    payload: Dict[str, Any],
    event_key: Optional[str] = None,
    state_path: Union[str, Path] = DEFAULT_STATE_PATH,
) -> bool:
    """
    Choose webhook by event_type (or by exit_priority for POSITION), format message, dedup by event_key+hash, then send.
    Phase 7.3: POSITION routes to CRITICAL or SIGNALS by exit_priority; FAST_CAPTURE gets 🔥 prefix.
    Returns True if message was sent successfully, False otherwise.
    """
    t = (event_type or "").strip().upper()
    if t == "POSITION":
        exit_priority = (payload.get("exit_priority") or "").strip().upper()
        webhook = _get_webhook_for_position(exit_priority)
        text = _format_message("POSITION", payload)
        if exit_priority == "FAST_CAPTURE":
            text = "🔥 " + text
    else:
        webhook = _get_webhook(t)
        text = _format_message(t, payload)
    if not webhook:
        logger.debug("[Slack] no webhook for %s, skip", event_type)
        return False
    if event_key is not None:
        new_hash = _state_hash(payload)
        if not should_send_alert(event_key, new_hash, state_path):
            logger.debug("[Slack] dedup skip %s", event_key)
            return False
    ok = send_slack_message(webhook, text)
    if ok:
        logger.info("[Slack] sent %s", event_type)
    else:
        logger.warning("[Slack] send failed for %s", event_type)
    return ok


def test_all_webhooks() -> Dict[str, bool]:
    """
    Dev-only: send one test message per webhook type (no dedup). Returns {event_type: success}.
    Phase 7.3: uses structured formats; includes POSITION (routed by exit_priority).
    """
    results: Dict[str, bool] = {}
    # SIGNAL
    webhook = _get_webhook("SIGNAL")
    if webhook:
        payload = {"symbol": "TEST", "tier": "A", "severity": "READY", "composite_score": 81.7, "strike": 175, "dte": 35, "delta": 0.34, "capital_required_estimate": 17500, "exit_base_target_pct": 0.60, "exit_extension_target_pct": 0.75, "exit_T1": 185.48, "exit_T2": 188.0, "mode": "CSP"}
        results["SIGNAL"] = send_slack_message(webhook, _format_message("SIGNAL", payload))
    else:
        results["SIGNAL"] = False
    # CRITICAL (position exit)
    webhook = _get_webhook("CRITICAL")
    if webhook:
        payload = {"symbol": "TEST", "mode": "CSP", "premium_capture_pct": 0.92, "dte": 3, "exit_priority": "EXPIRY_CRITICAL"}
        results["CRITICAL"] = send_slack_message(webhook, _format_message("CRITICAL", payload))
    else:
        results["CRITICAL"] = False
    # POSITION (routed by exit_priority; use ADVISORY -> SIGNALS)
    webhook = _get_webhook_for_position("ADVISORY")
    if webhook:
        payload = {"symbol": "TEST", "mode": "CSP", "premium_capture_pct": 0.65, "dte": 10, "exit_priority": "ADVISORY"}
        results["POSITION"] = send_slack_message(webhook, _format_message("POSITION", payload))
    else:
        results["POSITION"] = False
    # HEALTH
    webhook = _get_webhook("HEALTH")
    if webhook:
        payload = {"status": "FAIL", "failed_symbols": ["TEST"], "timestamp": "2026-02-13 20:27 EST"}
        results["HEALTH"] = send_slack_message(webhook, _format_message("HEALTH", payload))
    else:
        results["HEALTH"] = False
    # DAILY
    webhook = _get_webhook("DAILY")
    if webhook:
        payload = {"top_signals": [{"symbol": "NVDA", "tier": "A", "severity": "READY"}, {"symbol": "SPY", "tier": "B", "severity": "READY"}], "open_positions_count": 3, "total_capital_used": 52000, "exposure_pct": 34.0, "average_premium_capture": 0.41, "exit_alerts_today": 2}
        results["DAILY"] = send_slack_message(webhook, _format_message("DAILY", payload))
    else:
        results["DAILY"] = False
    return results


