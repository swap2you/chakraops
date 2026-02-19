# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 21.5: Slack sender status record for observability (last_send_at, last_send_ok, last_error, etc.).
   R21.5.1: Per-channel status (signals, daily, data_health, critical) + last_any_send_* for quick display."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

# R21.5.1: Canonical channel names for 4 webhooks (match UI and env)
SLACK_CHANNELS = ("signals", "daily", "data_health", "critical")


def _status_path() -> Path:
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[3] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "slack_status.json"


def _empty_channel() -> Dict[str, Any]:
    return {"last_send_at": None, "last_send_ok": None, "last_error": None, "last_payload_type": None}


def get_slack_status() -> Dict[str, Any]:
    """Return current Slack sender status. R21.5.1: includes channels map + last_any_send_*."""
    path = _status_path()
    if not path.exists():
        channels = {ch: _empty_channel() for ch in SLACK_CHANNELS}
        return {
            "channels": channels,
            "last_any_send_at": None,
            "last_any_send_ok": None,
            "last_any_send_error": None,
            # Backwards compat for UI that still reads flat fields
            "last_send_at": None,
            "last_send_ok": None,
            "last_error": None,
            "last_channel": None,
            "last_payload_type": None,
        }
    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.debug("Read slack_status failed: %s", e)
            channels = {ch: _empty_channel() for ch in SLACK_CHANNELS}
            return {
                "channels": channels,
                "last_any_send_at": None,
                "last_any_send_ok": None,
                "last_any_send_error": str(e),
                "last_send_at": None,
                "last_send_ok": None,
                "last_error": str(e),
                "last_channel": None,
                "last_payload_type": None,
            }
    channels = data.get("channels") or {}
    for ch in SLACK_CHANNELS:
        if ch not in channels:
            channels[ch] = _empty_channel()
    out = {
        "channels": channels,
        "last_any_send_at": data.get("last_any_send_at"),
        "last_any_send_ok": data.get("last_any_send_ok"),
        "last_any_send_error": data.get("last_any_send_error"),
        "last_send_at": data.get("last_send_at") or data.get("last_any_send_at"),
        "last_send_ok": data.get("last_send_ok") if "last_send_ok" in data else data.get("last_any_send_ok"),
        "last_error": data.get("last_error") or data.get("last_any_send_error"),
        "last_channel": data.get("last_channel"),
        "last_payload_type": data.get("last_payload_type"),
    }
    return out


def update_slack_status(
    channel: str,
    ok: bool,
    error: Optional[str] = None,
    payload_type: Optional[str] = None,
) -> None:
    """Update Slack sender status for a channel and last_any_* after a send attempt. R21.5.1: channel required."""
    if channel not in SLACK_CHANNELS:
        channel = "signals"
    now = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        path = _status_path()
        data: Dict[str, Any] = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        channels = data.get("channels") or {}
        for ch in SLACK_CHANNELS:
            if ch not in channels:
                channels[ch] = _empty_channel()
        channels[channel] = {
            "last_send_at": now,
            "last_send_ok": ok,
            "last_error": error if not ok else None,
            "last_payload_type": payload_type,
        }
        data["channels"] = channels
        data["last_any_send_at"] = now
        data["last_any_send_ok"] = ok
        data["last_any_send_error"] = error if not ok else None
        data["last_send_at"] = now
        data["last_send_ok"] = ok
        data["last_error"] = error if not ok else None
        data["last_channel"] = channel
        data["last_payload_type"] = payload_type
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=0)
        except Exception as e:
            logger.warning("Write slack_status failed: %s", e)
