# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.2: Slack alert dispatcher. Deterministic, deduplicated. No trading logic."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

ENV_WEBHOOK_CRITICAL = "SLACK_WEBHOOK_CRITICAL"
ENV_WEBHOOK_SIGNALS = "SLACK_WEBHOOK_SIGNALS"
ENV_WEBHOOK_HEALTH = "SLACK_WEBHOOK_HEALTH"
ENV_WEBHOOK_DAILY = "SLACK_WEBHOOK_DAILY"

DEFAULT_STATE_PATH = "artifacts/alerts/last_sent_state.json"


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


def _state_hash(payload: Dict[str, Any]) -> str:
    """Deterministic hash for dedup. No secrets in payload."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_state(state_path: Union[str, Path]) -> Dict[str, str]:
    path = Path(state_path)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: Dict[str, str], state_path: Union[str, Path]) -> None:
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


def _format_message(event_type: str, payload: Dict[str, Any]) -> str:
    """Clean Slack message. No raw JSON, no secrets. Emojis: 🟢 signal, 🔴 critical, ⚠️ health."""
    t = (event_type or "").strip().upper()
    if t == "SIGNAL":
        symbol = payload.get("symbol") or "?"
        tier = payload.get("tier") or "?"
        severity = payload.get("severity") or "?"
        score = payload.get("composite_score")
        score_s = str(score) if score is not None else "N/A"
        strike = payload.get("strike")
        strike_s = str(strike) if strike is not None else "N/A"
        return f"🟢 *Signal* {symbol} | tier {tier} | severity {severity} | score {score_s} | strike {strike_s}"
    if t == "CRITICAL":
        symbol = payload.get("symbol") or "?"
        position_id = str(payload.get("position_id") or "?")
        pid_short = position_id[:8] if len(position_id) >= 8 else position_id
        exit_signal = payload.get("exit_signal") or "?"
        reason = payload.get("exit_reason") or "?"
        return f"🔴 *Critical* {symbol} position {pid_short} | {exit_signal} | {reason}"
    if t == "HEALTH":
        failed = payload.get("failed_symbols") or payload.get("failed") or "?"
        return f"⚠️ *Health* gate not PASS | failed: {failed}"
    if t == "DAILY":
        top_count = payload.get("top_count") or 0
        positions_count = payload.get("open_positions_count") or 0
        exposure_pct = payload.get("exposure_pct")
        exp_s = f"{exposure_pct:.1f}%" if exposure_pct is not None else "N/A"
        alerts_count = payload.get("alerts_count") or 0
        return f"*Daily summary* | top {top_count} | open positions {positions_count} | exposure {exp_s} | alerts {alerts_count}"
    return f"*Alert* {t}"


def route_alert(
    event_type: str,
    payload: Dict[str, Any],
    event_key: Optional[str] = None,
    state_path: Union[str, Path] = DEFAULT_STATE_PATH,
) -> None:
    """
    Choose webhook by event_type, format message, dedup by event_key+hash, then send.
    If webhook missing: log and skip (no crash).
    """
    webhook = _get_webhook(event_type)
    if not webhook:
        logger.debug("[Slack] no webhook for %s, skip", event_type)
        return
    if event_key is not None:
        new_hash = _state_hash(payload)
        if not should_send_alert(event_key, new_hash, state_path):
            logger.debug("[Slack] dedup skip %s", event_key)
            return
    text = _format_message(event_type, payload)
    ok = send_slack_message(webhook, text)
    if ok:
        logger.info("[Slack] sent %s", event_type)
    else:
        logger.warning("[Slack] send failed for %s", event_type)


def test_all_webhooks() -> Dict[str, bool]:
    """
    Dev-only: send one test message per webhook type (no dedup). Returns {event_type: success}.
    Use from scripts/test_slack_alerts.py to verify Slack delivery end-to-end.
    """
    results: Dict[str, bool] = {}
    for event_type, payload in [
        ("SIGNAL", {"symbol": "TEST", "message": "Test signal", "tier": "A", "severity": "READY"}),
        ("CRITICAL", {"symbol": "TEST", "exit_signal": "EXIT_NOW", "position_id": "test-pos-1", "exit_reason": "Test"}),
        ("HEALTH", {"status": "FAIL", "failed_symbols": ["TEST"], "failed": "TEST"}),
        ("DAILY", {"summary": "Test daily summary", "top_count": 5, "open_positions_count": 0, "exposure_pct": 0.0, "alerts_count": 0}),
    ]:
        webhook = _get_webhook(event_type)
        if not webhook:
            results[event_type] = False  # missing webhook = not sent
            continue
        text = _format_message(event_type, payload)
        results[event_type] = send_slack_message(webhook, text)
    return results


