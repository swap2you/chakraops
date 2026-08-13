# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6: Slack delivery for alerts. Per-alert-type channel routing via webhook URLs."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

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
        from app.core.alerts.slack_dispatcher import post_slack_webhook
        from app.core.alerts.slack_status import update_slack_status
        channel = self._channel_for_alert(alert)
        webhook = self._webhook_for_alert(alert)
        if not webhook:
            logger.debug("[ALERTS] Slack not configured for %s; alert logged only: %s", channel, alert.summary[:50])
            update_slack_status(channel, ok=False, error="no_webhook", payload_type=alert.alert_type.value)
            return False
        blocks = self._build_blocks(alert)
        preview = self._mobile_preview_text(alert)
        payload = {"text": preview, "blocks": blocks}
        try:
            ok = post_slack_webhook(webhook, payload, channel_key=channel)
            if ok:
                logger.info("[ALERTS] Sent to Slack %s: %s %s", channel, alert.alert_type.value, alert.reason_code)
                update_slack_status(channel, ok=True, payload_type=alert.alert_type.value)
                return True
            update_slack_status(channel, ok=False, error="send_failed", payload_type=alert.alert_type.value)
            return False
        except Exception as e:
            logger.warning("[ALERTS] Slack send failed (%s): %s", channel, e)
            update_slack_status(channel, ok=False, error=str(e), payload_type=alert.alert_type.value)
            return False

    def _mobile_preview_text(self, alert: Alert) -> str:
        """Top-level text fallback for Slack mobile notifications (required with blocks)."""
        from app.core.alerts.slack_dispatcher import sanitize_slack_text
        from app.core.portfolio.capital_authority_r70 import robinhood_conflict_check_label

        at = alert.alert_type.value
        meta = alert.meta or {}
        sym = alert.symbol or "?"
        contract = meta.get("contract_key") or meta.get("contract_detail") or "position"
        qty = meta.get("quantity", "?")
        broker_state = meta.get("broker_state") or meta.get("snapshot_state") or "journal"
        freshness = str(meta.get("broker_freshness") or meta.get("freshness_state") or "").upper()
        conflict_label = meta.get("robinhood_conflict_label")
        if not conflict_label:
            conflict = meta.get("robinhood_conflict")
            if conflict is None and "robinhood_conflict" not in meta:
                conflict = None
            elif isinstance(conflict, bool):
                pass
            else:
                conflict = None
            conflict_label = robinhood_conflict_check_label(
                freshness or "UNAVAILABLE",
                conflict=conflict if isinstance(conflict, bool) else None,
            )
        if at == "POSITION_ABORT":
            live_claim = meta.get("live_confirmed") is True
            label = "ABORT · LIVE" if live_claim else "ABORT · advisory/unverified"
            text = (
                f"{label} · {contract} · qty={qty} · P/L={meta.get('pnl') or meta.get('pnl_dollars') or 'n/a'} · "
                f"{broker_state} · MANUAL ONLY — NO ORDER SENT"
            )
        elif at in ("POSITION_EXIT", "POSITION_HOLD", "POSITION_SCALE_OUT"):
            action = "CLOSE REVIEW" if at == "POSITION_EXIT" else ("HOLD" if at == "POSITION_HOLD" else "SCALE OUT")
            live_claim = meta.get("live_confirmed") is True
            prefix = action if live_claim else f"{action} · advisory/unverified"
            text = (
                f"{prefix} · {contract} · qty={qty} · "
                f"P/L={meta.get('pnl') or meta.get('pnl_dollars') or 'n/a'} · "
                f"{broker_state} · MANUAL ONLY — NO ORDER SENT"
            )
        elif at == "POSITION_ENTRY" or at == "SIGNAL":
            # Prefer rich candidate identity over generic "NEW SETUP · ?"
            cands = meta.get("candidates") or []
            primary = cands[0] if cands and isinstance(cands[0], dict) else {}
            display_sym = primary.get("symbol") or (sym if sym != "?" else None) or "MULTI"
            strategy = (
                meta.get("strategy")
                or primary.get("strategy")
                or meta.get("contract_detail")
                or alert.reason_code
            )
            score = meta.get("score") if meta.get("score") is not None else primary.get("score")
            band = meta.get("band") or primary.get("band")
            run_id = meta.get("run_id") or meta.get("eval_run_id") or ""
            qty_disp = meta.get("quantity")
            if qty_disp is None:
                qty_disp = meta.get("suggested_quantity") or primary.get("suggested_quantity") or primary.get("quantity")
                qty_tag = "suggested_qty"
            else:
                qty_tag = "qty"
            score_band = ""
            if score is not None or band:
                score_band = f" · score={score} band={band}"
            run_bit = f" · run={run_id}" if run_id else ""
            text = (
                f"NEW SETUP · {display_sym} · {strategy}{score_band} · "
                f"{qty_tag}={qty_disp if qty_disp is not None else 'n/a'} · "
                f"{conflict_label}{run_bit} · MANUAL ONLY — NO ORDER SENT"
            )
        elif at in ("DATA_HEALTH", "SYSTEM", "REGIME_CHANGE", "PORTFOLIO_RISK_WARN"):
            text = (
                f"BROKER/ORATS/SYSTEM ISSUE · {alert.summary[:120]} · "
                f"{alert.action_hint[:80]} · MANUAL ONLY — NO ORDER SENT"
            )
        elif at == "PORTFOLIO_RISK_BLOCK":
            text = f"ABORT · portfolio block · {alert.summary[:120]} · MANUAL ONLY — NO ORDER SENT"
        else:
            text = f"{at} · {sym} · {alert.summary[:120]} · MANUAL ONLY — NO ORDER SENT"
        return sanitize_slack_text(text)

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
        """Expanded Slack format for lifecycle / position action alerts."""
        from app.core.alerts.slack_dispatcher import sanitize_slack_text

        meta = alert.meta or {}
        at = alert.alert_type.value
        sym = alert.symbol or ""
        live_confirmed = meta.get("live_confirmed") is True
        parts = []

        def _advisory_action() -> str:
            return (
                "Action: MANUAL REVIEW REQUIRED — "
                "POSITION NOT CONFIRMED BY FRESH BROKER SNAPSHOT — "
                "REFRESH ROBINHOOD BEFORE ACTING"
            )

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
            if live_confirmed:
                parts.append("Action: EXIT 1 CONTRACT NOW")
            else:
                parts.append(_advisory_action())
        elif at == "POSITION_EXIT":
            if alert.reason_code == "STOP_LOSS":
                parts.append(f"🔴 STOP LOSS — {sym}")
                parts.append("Price breached stop")
                if live_confirmed:
                    parts.append("Action: EXIT IMMEDIATELY")
                else:
                    parts.append(_advisory_action())
            else:
                parts.append(f"🟠 CLOSE REVIEW — {sym}")
                parts.append(meta.get("reason_detail", "Target 2 hit"))
                if live_confirmed:
                    parts.append("Action: EXIT ALL REMAINING")
                else:
                    parts.append(_advisory_action())
        elif at == "POSITION_ABORT":
            parts.append(f"🚨 ABORT — {sym}")
            parts.append("Regime no longer allowed")
            if live_confirmed:
                parts.append("Action: CLOSE POSITION ASAP")
            else:
                parts.append(_advisory_action())
        elif at == "POSITION_HOLD":
            parts.append(f"⏸️ HOLD — {sym}")
            parts.append(meta.get("reason_detail", "Data unreliable"))
            parts.append("Action: HOLD — DATA UNRELIABLE")
        else:
            parts.append(f"• {at} — {sym}")
            parts.append(alert.summary)
            parts.append(f"Action: {alert.action_hint}")

        # Required expanded fields for every position action message.
        parts.append("")
        parts.append(f"Account: {meta.get('account_alias') or 'manual'}")
        parts.append(f"Broker source: {meta.get('broker_source') or 'manual_journal'}")
        if meta.get("broker_as_of") or meta.get("snapshot_as_of"):
            parts.append(f"Broker snapshot as_of: {meta.get('broker_as_of') or meta.get('snapshot_as_of')}")
        age = meta.get("snapshot_age") or meta.get("snapshot_age_sec")
        # Prefer effective age-based broker_freshness / freshness_state over raw snap tag.
        freshness = (
            meta.get("broker_freshness")
            or meta.get("freshness_state")
            or meta.get("freshness")
            or meta.get("snapshot_freshness")
        )
        if age is not None or freshness:
            parts.append(f"Snapshot age/freshness: {age if age is not None else 'n/a'} / {freshness or 'n/a'}")
        parts.append(f"Symbol: {sym}")
        parts.append(f"Strategy: {meta.get('strategy') or 'n/a'}")
        if meta.get("expiration") or meta.get("strike") is not None or meta.get("right"):
            parts.append(
                f"Option: exp={meta.get('expiration') or 'n/a'} "
                f"strike={meta.get('strike') if meta.get('strike') is not None else 'n/a'} "
                f"right={meta.get('right') or 'n/a'}"
            )
        parts.append(f"Quantity: {meta.get('quantity', 'n/a')}")
        if meta.get("entry_credit") is not None or meta.get("cost_basis") is not None:
            parts.append(
                f"Entry/cost: credit={meta.get('entry_credit', 'n/a')} basis={meta.get('cost_basis', 'n/a')}"
            )
        if meta.get("mark") is not None:
            parts.append(f"Mark: {meta.get('mark')} @ {meta.get('mark_ts') or 'n/a'}")
        pnl = meta.get("pnl_dollars") if meta.get("pnl_dollars") is not None else meta.get("pnl")
        pnl_pct = meta.get("pnl_pct")
        if pnl is not None or pnl_pct is not None:
            parts.append(f"P/L: {pnl if pnl is not None else 'n/a'} ({pnl_pct if pnl_pct is not None else 'n/a'}%)")
        if meta.get("dte") is not None:
            parts.append(f"DTE: {meta.get('dte')}")
        parts.append(f"Recommendation: {meta.get('recommendation') or alert.action_hint}")
        trigger = meta.get("trigger") or alert.reason_code
        reasons = meta.get("reasons") or []
        if isinstance(reasons, list):
            reason_txt = "; ".join(str(r) for r in reasons[:2])
        else:
            reason_txt = str(reasons)
        parts.append(f"Trigger: {trigger}" + (f" — {reason_txt}" if reason_txt else ""))
        parts.append(f"Run ID: {meta.get('eval_run_id') or meta.get('run_id') or 'n/a'}")
        # Never describe a local/manual/history row as a LIVE Robinhood open.
        parts.append(f"Position class: {meta.get('broker_state') or 'manual journal — not a LIVE Robinhood open'}")
        parts.append("MANUAL ONLY — NO ORDER SENT")

        text = sanitize_slack_text("\n".join(parts))
        section = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        }
        context = {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": sanitize_slack_text(f"{alert.created_at} | {alert.reason_code}")}],
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
        from app.core.alerts.slack_dispatcher import get_webhook_for_channel, post_slack_webhook
        from app.core.alerts.slack_status import update_slack_status

        webhook = get_webhook_for_channel(channel)
        if not webhook:
            logger.debug("[ALERTS] Slack not configured for %s; eval summary skipped", channel)
            update_slack_status(channel, ok=False, error="Slack not configured", payload_type="EVAL_SUMMARY")
            return False
        text = self._format_eval_summary(payload)
        try:
            ok = post_slack_webhook(webhook, {"text": text}, channel_key=channel or "daily")
            if ok:
                logger.info("[ALERTS] Sent EVAL_SUMMARY to %s run_id=%s", channel, payload.get("run_id", "?"))
                update_slack_status(channel, ok=True, payload_type="EVAL_SUMMARY")
                return True
            update_slack_status(channel, ok=False, error="send_failed", payload_type="EVAL_SUMMARY")
            return False
        except Exception as e:
            logger.warning("[ALERTS] EVAL_SUMMARY send failed (%s): %s", channel, e)
            update_slack_status(channel, ok=False, error=str(e), payload_type="EVAL_SUMMARY")
            return False

    def _format_eval_summary(self, p: Dict[str, Any]) -> str:
        """Concise one-message format for EVAL_SUMMARY with mobile-friendly first line."""
        from app.core.alerts.slack_dispatcher import sanitize_slack_text

        mode = p.get("mode", "LIVE")
        total = p.get("total", 0)
        eligible = p.get("eligible", 0)
        urgent = 0
        alerts_sent = p.get("alerts_sent") or {}
        if isinstance(alerts_sent, dict):
            urgent = int(alerts_sent.get("critical") or 0)
        broker_state = p.get("broker_state") or "UNAVAILABLE"
        open_positions = p.get("open_positions")
        if open_positions is None:
            open_positions = p.get("broker_open_display", "UNKNOWN")
        ts = p.get("timestamp") or ""
        actionability = p.get("actionability") or p.get("data_health_state") or ""
        if str(broker_state).upper() == "FRESH" and str(actionability).upper() not in (
            "DATA NOT ACTIONABLE",
            "BLOCKED",
            "ORATS_ERROR",
            "ERROR",
        ):
            preview = (
                f"{mode} eval complete · evaluated={total} · qualified={eligible} · "
                f"broker={broker_state} · broker open={open_positions} · urgent={urgent} · {ts}"
            )
        elif str(broker_state).upper() == "STALE":
            preview = (
                f"{mode} eval complete · evaluated={total} · qualified={eligible} · "
                f"broker=STALE · broker open=UNKNOWN · DATA NOT ACTIONABLE · {ts}"
            )
        else:
            preview = (
                f"{mode} eval complete · evaluated={total} · qualified={eligible} · "
                f"broker={broker_state} · broker open=UNKNOWN · BROKER CHECK NOT PERFORMED · {ts}"
            )
        if str(actionability).upper() in ("DATA NOT ACTIONABLE", "ORATS_ERROR", "ERROR", "WARN", "DELAYED"):
            if "DATA NOT ACTIONABLE" not in preview and "BROKER CHECK" not in preview:
                preview = f"{preview} · DATA NOT ACTIONABLE ({actionability})"

        lines = [
            sanitize_slack_text(preview),
            "",
            "📊 *ChakraOps Eval Summary*",
            f"Mode: {mode} | Run: `{p.get('run_id', '?')}` | {ts}",
            f"Account: {p.get('account_alias') or 'acct_individual'}",
            f"Broker: {broker_state} | as_of={p.get('broker_as_of') or 'n/a'} | age_min={p.get('broker_age_minutes') if p.get('broker_age_minutes') is not None else 'n/a'}",
            f"Broker open positions: {open_positions}",
            f"ORATS/data-health: {p.get('orats_state') or actionability or 'n/a'}",
            "",
            f"*Counts:* total={total} eligible={eligible} A={p.get('a_tier', 0)} B={p.get('b_tier', 0)} blocked={p.get('blocked', 0)}",
            "MANUAL ONLY — NO ORDER SENT",
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
        if alerts_sent:
            lines.append(
                f"*Alerts this run:* signals={alerts_sent.get('signals', 0)} "
                f"data_health={alerts_sent.get('data_health', 0)} critical={alerts_sent.get('critical', 0)}"
            )
        dur = p.get("duration_ms")
        if dur is not None:
            lines.append(f"Duration: {dur:.0f}ms | last_run_ok: {p.get('last_run_ok', '?')}")
        return sanitize_slack_text("\n".join(lines))
