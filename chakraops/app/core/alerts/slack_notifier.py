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
    """Send alerts to Slack with formatted blocks. R21.5.1: Routes by channel (signals, daily, data_health, critical)."""

    def __init__(self, config: Dict[str, Any]):
        self._config = config or {}
        self._default_webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        channels = (self._config.get("slack") or {}).get("channels") or {}
        self._webhooks: Dict[str, str] = {}
        for k, v in channels.items():
            if isinstance(v, str) and v.strip().startswith("http"):
                self._webhooks[k] = v.strip()

    def _channel_for_alert(self, alert: Alert) -> str:
        """R21.5.1: Map alert type to channel: signals | daily | data_health | critical."""
        at = alert.alert_type.value
        # critical: PANIC/urgent failures
        if at == "POSITION_ABORT":
            return "critical"
        if at == "PORTFOLIO_RISK_BLOCK":
            return "critical"
        if at == "POSITION_EXIT" and (alert.reason_code == "STOP_LOSS" or alert.severity.value == "CRITICAL"):
            return "critical"
        # data_health: ORATS/data-sufficiency/sanity warnings
        if at == "DATA_HEALTH":
            return "data_health"
        if at == "PORTFOLIO_RISK_WARN":
            return "data_health"
        if at == "SYSTEM":
            return "data_health"
        if at == "REGIME_CHANGE":
            return "data_health"
        # signals: eligibility/entry/exit signals
        if at in ("SIGNAL", "POSITION_ENTRY", "POSITION_SCALE_OUT", "POSITION_EXIT", "POSITION_HOLD"):
            return "signals"
        # default
        return "signals"

    def _webhook_for_alert(self, alert: Alert) -> Optional[str]:
        from app.core.alerts.slack_dispatcher import get_webhook_for_channel
        channel = self._channel_for_alert(alert)
        url = get_webhook_for_channel(channel)
        if url:
            return url
        return self._webhooks.get(alert.alert_type.value) or self._default_webhook or None

    def send(self, alert: Alert) -> bool:
        """Send one alert to Slack. Returns True if sent, False if skipped (no webhook) or failed. R21.5.1: updates per-channel status."""
        from app.core.alerts.slack_status import update_slack_status
        channel = self._channel_for_alert(alert)
        webhook = self._webhook_for_alert(alert)
        if not webhook:
            logger.debug("[ALERTS] Slack not configured for %s; alert logged only: %s", channel, alert.summary[:50])
            update_slack_status(channel, ok=False, error="no_webhook", payload_type=alert.alert_type.value)
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
            logger.info("[ALERTS] Sent to Slack %s: %s %s", channel, alert.alert_type.value, alert.reason_code)
            update_slack_status(channel, ok=True, payload_type=alert.alert_type.value)
            return True
        except requests.RequestException as e:
            logger.warning("[ALERTS] Slack send failed (%s): %s", channel, e)
            update_slack_status(channel, ok=False, error=str(e), payload_type=alert.alert_type.value)
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

    def send_eval_summary(self, channel: str, payload: Dict[str, Any]) -> bool:
        """R21.5.2: Send EVAL_SUMMARY to channel (daily). Updates slack_status with payload_type EVAL_SUMMARY."""
        from app.core.alerts.slack_dispatcher import get_webhook_for_channel
        from app.core.alerts.slack_status import update_slack_status

        webhook = get_webhook_for_channel(channel)
        if not webhook:
            logger.debug("[ALERTS] Slack not configured for %s; eval summary skipped", channel)
            update_slack_status(channel, ok=False, error="Slack not configured", payload_type="EVAL_SUMMARY")
            return False
        text = self._format_eval_summary(payload)
        try:
            resp = requests.post(
                webhook,
                json={"text": text},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("[ALERTS] Sent EVAL_SUMMARY to %s run_id=%s", channel, payload.get("run_id", "?"))
            update_slack_status(channel, ok=True, payload_type="EVAL_SUMMARY")
            return True
        except requests.RequestException as e:
            logger.warning("[ALERTS] EVAL_SUMMARY send failed (%s): %s", channel, e)
            update_slack_status(channel, ok=False, error=str(e), payload_type="EVAL_SUMMARY")
            return False

    def _format_eval_summary(self, p: Dict[str, Any]) -> str:
        """Concise one-message format for EVAL_SUMMARY."""
        lines = [
            "📊 *ChakraOps Eval Summary*",
            f"Mode: {p.get('mode', '?')} | Run: `{p.get('run_id', '?')}` | {p.get('timestamp', '')}",
            "",
            f"*Counts:* total={p.get('total', 0)} eligible={p.get('eligible', 0)} A={p.get('a_tier', 0)} B={p.get('b_tier', 0)} blocked={p.get('blocked', 0)}",
        ]
        top = p.get("top_eligibles") or []
        if top:
            lines.append("*Top eligibles:*")
            for e in top[:3]:
                sym = e.get("symbol", "?")
                strat = e.get("strategy", "CSP")
                score = e.get("score")
                band = e.get("band", "?")
                lines.append(f"  • {sym} {strat} score={score} band={band}")
        alerts_sent = p.get("alerts_sent")
        if alerts_sent:
            lines.append(f"*Alerts this run:* signals={alerts_sent.get('signals', 0)} data_health={alerts_sent.get('data_health', 0)} critical={alerts_sent.get('critical', 0)}")
        dur = p.get("duration_ms")
        if dur is not None:
            lines.append(f"Duration: {dur:.0f}ms | last_run_ok: {p.get('last_run_ok', '?')}")
        return "\n".join(lines)
