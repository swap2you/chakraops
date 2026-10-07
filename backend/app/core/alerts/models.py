# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Alert model for Phase 6: stage-aware, deduplicated alerts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class AlertType(str, Enum):
    DATA_HEALTH = "DATA_HEALTH"
    REGIME_CHANGE = "REGIME_CHANGE"
    SIGNAL = "SIGNAL"
    SYSTEM = "SYSTEM"
    # Phase 2C: Lifecycle alerts (position directive)
    POSITION_ENTRY = "POSITION_ENTRY"
    POSITION_SCALE_OUT = "POSITION_SCALE_OUT"
    POSITION_EXIT = "POSITION_EXIT"
    POSITION_ABORT = "POSITION_ABORT"
    POSITION_HOLD = "POSITION_HOLD"
    # Phase 3: Portfolio risk alerts
    PORTFOLIO_RISK_WARN = "PORTFOLIO_RISK_WARN"
    PORTFOLIO_RISK_BLOCK = "PORTFOLIO_RISK_BLOCK"


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


@dataclass
class Alert:
    """Core alert model: actionable, with fingerprint for deduplication."""
    alert_type: AlertType
    severity: Severity
    reason_code: str
    summary: str
    action_hint: str
    fingerprint: str
    created_at: str
    stage: Optional[str] = None
    symbol: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "stage": self.stage,
            "symbol": self.symbol,
            "reason_code": self.reason_code,
            "summary": self.summary,
            "action_hint": self.action_hint,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
            "meta": self.meta,
        }
