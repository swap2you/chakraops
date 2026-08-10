# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R54 read-only advisory monitor worker (legacy scheduler stays off)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SIGNAL_TYPES = frozenset(
    {
        "TAKE_PROFIT",
        "TIME_EXIT",
        "THESIS_BREAK",
        "ROLL_REVIEW",
        "ASSIGNMENT_RISK",
        "CC_READY",
        "CALL_AWAY_RISK",
        "EARNINGS_RISK",
        "CONCENTRATION_RISK",
        "STALE_DATA",
        "BROKER_DISCONNECTED",
        "NEW_OPPORTUNITY",
        "OPPORTUNITY_INVALIDATED",
    }
)


@dataclass
class AdvisorySignal:
    signal_type: str
    symbol: str = ""
    message: str = ""
    as_of: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "symbol": self.symbol,
            "message": self.message,
            "as_of": self.as_of,
            "payload": self.payload,
            "manual_only": True,
            "trade_execution": False,
            "broker_writes": False,
        }


def evaluate_broker_health_signals(status: Dict[str, Any], snapshot: Optional[Dict[str, Any]]) -> List[AdvisorySignal]:
    signals: List[AdvisorySignal] = []
    if not status.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE"):
        signals.append(
            AdvisorySignal(
                signal_type="BROKER_DISCONNECTED",
                message="Robinhood MCP read-only unavailable/unauthenticated",
                payload={"status": status.get("status"), "blocker": status.get("blocker")},
            )
        )
    if snapshot and (snapshot.get("stale") or status.get("status") == "UNAUTHENTICATED"):
        signals.append(
            AdvisorySignal(
                signal_type="STALE_DATA",
                message="Broker snapshot stale or missing fresh sync",
                payload={"fetched_at": snapshot.get("fetched_at")},
            )
        )
    return signals


class AdvisoryMonitorWorker:
    """Separate from legacy schedulers. Read-only; never places orders."""

    def __init__(self, *, interval_sec: float = 60.0) -> None:
        self.interval_sec = max(5.0, float(interval_sec))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_signals: List[AdvisorySignal] = []
        self.last_run_at: Optional[str] = None
        self.running = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="r54-advisory-monitor", daemon=True)
        self._thread.start()
        self.running = True

    def stop(self) -> None:
        self._stop.set()
        self.running = False

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.warning("advisory monitor cycle failed: %s", type(exc).__name__)
            self._stop.wait(self.interval_sec)

    def run_once(self) -> List[AdvisorySignal]:
        from app.core.broker.status import robinhood_mcp_read_only_status
        from app.core.broker.snapshot_store import load_snapshot

        status = robinhood_mcp_read_only_status()
        snap_obj = load_snapshot("acct_individual")
        snap = snap_obj.to_dict() if snap_obj else None
        signals = evaluate_broker_health_signals(status, snap)
        self.last_signals = signals
        self.last_run_at = datetime.now(timezone.utc).isoformat()
        self._persist_state()
        self._dispatch_slack(signals)
        return signals

    def _state_path(self) -> Path:
        data_dir = os.environ.get("DATA_DIR")
        base = Path(data_dir).resolve() if data_dir else Path(__file__).resolve().parents[3] / "data"
        base.mkdir(parents=True, exist_ok=True)
        return base / "advisory_monitor_r54.json"

    def _persist_state(self) -> None:
        payload = {
            "last_run_at": self.last_run_at,
            "running": self.running,
            "signals": [s.to_dict() for s in self.last_signals],
            "manual_only": True,
            "trade_execution": False,
            "legacy_scheduler": False,
        }
        try:
            self._state_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("failed to persist advisory monitor state")

    def _dispatch_slack(self, signals: List[AdvisorySignal]) -> None:
        if not signals:
            return
        try:
            from app.core.alerts.slack_dispatcher import is_slack_configured, send_slack_message, get_webhook_for_channel
        except Exception:
            return
        if not is_slack_configured():
            return
        webhook = get_webhook_for_channel("ops") or get_webhook_for_channel("alerts")
        if not webhook:
            return
        for sig in signals:
            text = f"[ChakraOps advisory] {sig.signal_type}: {sig.message} ({sig.symbol or 'n/a'})"
            try:
                send_slack_message(webhook, text)
            except Exception:
                logger.warning("slack advisory dispatch failed")


_WORKER: Optional[AdvisoryMonitorWorker] = None


def get_monitor_worker() -> AdvisoryMonitorWorker:
    global _WORKER
    if _WORKER is None:
        _WORKER = AdvisoryMonitorWorker(interval_sec=float(os.environ.get("R54_MONITOR_INTERVAL_SEC") or 60))
    return _WORKER


def monitor_status() -> Dict[str, Any]:
    w = get_monitor_worker()
    return {
        "running": w.running,
        "last_run_at": w.last_run_at,
        "signal_count": len(w.last_signals),
        "signals": [s.to_dict() for s in w.last_signals],
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "legacy_scheduler_enabled": False,
    }
