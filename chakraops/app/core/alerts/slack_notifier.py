# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6: Slack delivery for alerts. Per-alert-type channel routing via webhook URLs."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

from app.core.alerts.models import Alert

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Send alerts to Slack with formatted blocks. One webhook per channel/type."""

    def __init__(self, config: Dict[str, Any]):
        self._config = config or {}
        self._default_webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        channels = (self._config.get("slack") or {}).get("channels") or {}
        self._webhooks: Dict[str, str] = {}
        for k, v in channels.items():
            if isinstance(v, str) and v.strip().startswith("http"):
                self._webhooks[k] = v.strip()

    def _webhook_for_alert(self, alert: Alert) -> Optional[str]:
        at = alert.alert_type.value
        return self._webhooks.get(at) or self._default_webhook or None

    def send(self, alert: Alert) -> bool:
        """Send one alert to Slack. Returns True if sent, False if skipped (no webhook) or failed."""
        webhook = self._webhook_for_alert(alert)
        if not webhook:
            logger.debug("[ALERTS] Slack not configured; alert logged only: %s", alert.summary[:50])
            return False
        blocks = self._build_blocks(alert)
        try:
            resp = requests.post(
                webhook,
                json={"blocks": blocks},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("[ALERTS] Sent to Slack: %s %s", alert.alert_type.value, alert.reason_code)
            return True
        except requests.RequestException as e:
            logger.warning("[ALERTS] Slack send failed: %s", e)
            return False

    def _build_blocks(self, alert: Alert) -> list:
        severity_emoji = {"INFO": "ℹ️", "WARN": "⚠️", "CRITICAL": "🔴"}.get(alert.severity.value, "•")
        header = f"{severity_emoji} *ChakraOps Alert* `{alert.alert_type.value}`"
        if alert.severity.value != "INFO":
            header += f" [{alert.severity.value}]"
        section_header = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": header},
        }
        section_summary = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary:* {alert.summary}"},
        }
        section_action = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Action:* {alert.action_hint}"},
        }
        context_parts = [f"<{alert.reason_code}>"]
        if alert.symbol:
            context_parts.append(f"Symbol: {alert.symbol}")
        if alert.stage:
            context_parts.append(f"Stage: {alert.stage}")
        context_parts.append(alert.created_at)
        context = {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": " | ".join(context_parts)}],
        }
        return [section_header, section_summary, section_action, context]
