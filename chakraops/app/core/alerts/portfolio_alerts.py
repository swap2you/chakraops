# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3: Portfolio alert builders — PORTFOLIO_RISK_WARN, PORTFOLIO_RISK_BLOCK."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.alerts.models import Alert, AlertType, Severity

logger = logging.getLogger(__name__)


def _make_fingerprint(alert_type: str, reason: str, extra: str = "") -> str:
    raw = f"PORTFOLIO|{alert_type}|{reason}|{extra}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def build_portfolio_alerts_for_run(
    summary: Any,
    risk_flags: List[Any],
    config: Dict[str, Any],
) -> List[Alert]:
    """
    Build portfolio risk alerts during run completion.

    PORTFOLIO_RISK_WARN: approaching threshold (e.g. util > 0.85 * max)
    PORTFOLIO_RISK_BLOCK: threshold breached (util > max, over symbol, over sector, etc.)

    Cooldown: 12h per alert type (configurable via portfolio_alert_cooldown_hours).
    """
    alerts: List[Alert] = []
    now = datetime.now(timezone.utc).isoformat()
    enabled = set(config.get("enabled_alert_types") or [])

    if "PORTFOLIO_RISK_BLOCK" not in enabled and "PORTFOLIO_RISK_WARN" not in enabled:
        return alerts

    if not summary or not risk_flags:
        return alerts

    # Build top 3 risk reasons from flags
    top_reasons = [f.message for f in risk_flags[:3]]
    summary_text = (
        f"Utilization {getattr(summary, 'capital_utilization_pct', 0):.1%}, "
        f"{getattr(summary, 'open_positions_count', 0)} open positions"
    )

    # BLOCK: any error-level flag
    block_flags = [f for f in risk_flags if getattr(f, "severity", "") == "error"]
    if block_flags and "PORTFOLIO_RISK_BLOCK" in enabled:
        fp = _make_fingerprint("PORTFOLIO_RISK_BLOCK", block_flags[0].code, summary_text)
        alerts.append(Alert(
            alert_type=AlertType.PORTFOLIO_RISK_BLOCK,
            severity=Severity.CRITICAL,
            reason_code=block_flags[0].code,
            summary=summary_text + ". " + "; ".join(top_reasons),
            action_hint="Review portfolio and risk profile. Reduce exposure or adjust thresholds.",
            fingerprint=fp,
            created_at=now,
            stage=None,
            symbol=None,
            meta={
                "utilization_pct": getattr(summary, "capital_utilization_pct", 0),
                "open_positions": getattr(summary, "open_positions_count", 0),
                "top_reasons": top_reasons,
            },
        ))

    # WARN: approaching threshold (no block flags but util high)
    if not block_flags and "PORTFOLIO_RISK_WARN" in enabled:
        util = getattr(summary, "capital_utilization_pct", 0)
        # Simple heuristic: util > 80% of typical max (0.35) = 0.28
        if util > 0.25:
            fp = _make_fingerprint("PORTFOLIO_RISK_WARN", "APPROACHING_THRESHOLD", summary_text)
            alerts.append(Alert(
                alert_type=AlertType.PORTFOLIO_RISK_WARN,
                severity=Severity.WARN,
                reason_code="APPROACHING_THRESHOLD",
                summary=summary_text + ". Consider reducing exposure.",
                action_hint="Monitor portfolio; approaching risk thresholds.",
                fingerprint=fp,
                created_at=now,
                stage=None,
                symbol=None,
                meta={
                    "utilization_pct": util,
                    "open_positions": getattr(summary, "open_positions_count", 0),
                },
            ))

    return alerts
