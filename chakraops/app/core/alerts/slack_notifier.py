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
        # Phase 2C: Lifecycle alerts use exact Slack format
        if alert.meta and alert.meta.get("lifecycle_format") == "directive":
            return self._build_lifecycle_blocks(alert)
        # Phase 3: Portfolio risk alerts
        if alert.alert_type.value in ("PORTFOLIO_RISK_WARN", "PORTFOLIO_RISK_BLOCK"):
            return self._build_portfolio_blocks(alert)
        # Default format for non-lifecycle alerts
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

    def _build_lifecycle_blocks(self, alert: Alert) -> list:
        """Phase 2C: Exact Slack format for lifecycle directive alerts."""
        meta = alert.meta or {}
        at = alert.alert_type.value
        sym = alert.symbol or ""
        parts = []

        if at == "POSITION_ENTRY":
            parts.append(f"🟢 ENTRY — {sym} ({meta.get('strategy', 'CSP')})")
            parts.append(meta.get("contract_detail", "Sell put") or "—")
            if meta.get("premium") is not None:
                parts.append(f"Premium: ${meta['premium']:.2f}")
            if meta.get("capital_used") is not None:
                parts.append(f"Capital Used: ${meta['capital_used']:,.0f}")
            parts.append("Action: ENTER MANUALLY")
        elif at == "POSITION_SCALE_OUT":
            parts.append(f"🟡 SCALE OUT — {sym}")
            parts.append("Target 1 hit")
            parts.append("Action: EXIT 1 CONTRACT NOW")
        elif at == "POSITION_EXIT":
            if alert.reason_code == "STOP_LOSS":
                parts.append(f"🔴 STOP LOSS — {sym}")
                parts.append("Price breached stop")
                parts.append("Action: EXIT IMMEDIATELY")
            else:
                parts.append(f"🟠 EXIT — {sym}")
                parts.append(meta.get("reason_detail", "Target 2 hit"))
                parts.append("Action: EXIT ALL REMAINING")
        elif at == "POSITION_ABORT":
            parts.append(f"🚨 ABORT — {sym}")
            parts.append("Regime no longer allowed")
            parts.append("Action: CLOSE POSITION ASAP")
        elif at == "POSITION_HOLD":
            parts.append(f"⏸️ HOLD — {sym}")
            parts.append(meta.get("reason_detail", "Data unreliable"))
            parts.append("Action: HOLD — DATA UNRELIABLE")
        else:
            parts.append(f"• {at} — {sym}")
            parts.append(alert.summary)
            parts.append(f"Action: {alert.action_hint}")

        text = "\n".join(parts)
        section = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        }
        context = {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"{alert.created_at} | {alert.reason_code}"}],
        }
        return [section, context]

    def _build_portfolio_blocks(self, alert: Alert) -> list:
        """Phase 3: Portfolio risk alert format — utilization %, top reasons."""
        meta = alert.meta or {}
        at = alert.alert_type.value
        emoji = "⚠️" if at == "PORTFOLIO_RISK_WARN" else "🔴"
        parts = [f"{emoji} *Portfolio Risk* — {at.replace('PORTFOLIO_RISK_', '')}"]
        parts.append(alert.summary)
        top_reasons = meta.get("top_reasons", [])
        if top_reasons:
            parts.append("")
            parts.append("*Top reasons:*")
            for r in top_reasons[:3]:
                parts.append(f"• {r}")
        parts.append("")
        parts.append(f"*Action:* {alert.action_hint}")
        text = "\n".join(parts)
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": alert.created_at}]},
        ]
