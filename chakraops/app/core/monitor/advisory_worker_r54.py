# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R54/R65 read-only advisory monitor worker (legacy scheduler stays off)."""

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

# R65 signal vocabulary (state-change only; no unchanged spam).
SIGNAL_TYPES = frozenset(
    {
        "NEW_OPPORTUNITY",
        "OPPORTUNITY_INVALIDATED",
        "TAKE_PROFIT",
        "THESIS_BREAK",
        "TIME_EXIT",
        "ROLL_REVIEW",
        "ASSIGNMENT_RISK",
        "CC_READY",
        "CALL_AWAY_RISK",
        "EARNINGS_EVENT_RISK",
        "CONCENTRATION_RISK",
        "BROKER_STALE",
        "ORATS_STALE",
        "SYSTEM_DEGRADED",
        # Back-compat aliases
        "EARNINGS_RISK",
        "STALE_DATA",
        "BROKER_DISCONNECTED",
    }
)


@dataclass
class AdvisorySignal:
    signal_type: str
    symbol: str = ""
    message: str = ""
    as_of: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: Dict[str, Any] = field(default_factory=dict)
    deep_link: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "symbol": self.symbol,
            "message": self.message,
            "as_of": self.as_of,
            "payload": self.payload,
            "deep_link": self.deep_link or build_advisory_deep_link(self.signal_type, self.symbol),
            "manual_only": True,
            "trade_execution": False,
            "broker_writes": False,
        }


def public_base_url() -> str:
    return (os.environ.get("APP_PUBLIC_URL") or "https://chakraops.cloud").rstrip("/")


def build_advisory_deep_link(signal_type: str, symbol: str = "") -> str:
    """Deep link into chakraops.cloud UI — never a broker execution URL."""
    base = public_base_url()
    sym = (symbol or "").strip().upper()
    st = (signal_type or "").strip().upper()
    if st in {"BROKER_STALE", "BROKER_DISCONNECTED", "STALE_DATA", "SYSTEM_DEGRADED"}:
        return f"{base}/portfolio?tab=overview"
    if st in {"CONCENTRATION_RISK"}:
        return f"{base}/portfolio?tab=risk"
    if st in {"ORATS_STALE"}:
        return f"{base}/ops"
    if sym:
        return f"{base}/symbol-diagnostics?symbol={sym}"
    return f"{base}/portfolio?tab=overview"


def evaluate_broker_health_signals(status: Dict[str, Any], snapshot: Optional[Dict[str, Any]]) -> List[AdvisorySignal]:
    signals: List[AdvisorySignal] = []
    st = (status.get("status") or "").strip().upper()
    if not status.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE") or st in {"UNAUTHENTICATED", "AUTH_REQUIRED"}:
        signals.append(
            AdvisorySignal(
                signal_type="BROKER_DISCONNECTED",
                message="Robinhood MCP read-only unavailable/unauthenticated",
                payload={"status": status.get("status"), "blocker": status.get("blocker")},
            )
        )
    if snapshot and (snapshot.get("stale") or st == "STALE" or status.get("snapshot_stale")):
        signals.append(
            AdvisorySignal(
                signal_type="BROKER_STALE",
                message="Broker snapshot stale or missing fresh sync",
                payload={"fetched_at": snapshot.get("fetched_at"), "status": st},
            )
        )
    if st == "ERROR":
        signals.append(
            AdvisorySignal(
                signal_type="SYSTEM_DEGRADED",
                message="Broker integration reported ERROR",
                payload={"status": st, "blocker": status.get("blocker")},
            )
        )
    return signals


def evaluate_orats_health_signals(*, orats_ok: Optional[bool] = None) -> List[AdvisorySignal]:
    if orats_ok is False:
        return [
            AdvisorySignal(
                signal_type="ORATS_STALE",
                message="ORATS data health degraded or stale",
                payload={"provider": "orats"},
            )
        ]
    return []


def dedupe_state_change_signals(
    previous: List[Dict[str, Any]],
    current: List[AdvisorySignal],
) -> List[AdvisorySignal]:
    """Emit only state-change signals (no unchanged spam)."""
    prev_keys = {
        f"{(p.get('signal_type') or '').upper()}|{(p.get('symbol') or '').upper()}|{(p.get('message') or '')}"
        for p in previous
    }
    out: List[AdvisorySignal] = []
    for sig in current:
        key = f"{sig.signal_type.upper()}|{sig.symbol.upper()}|{sig.message}"
        if key not in prev_keys:
            out.append(sig)
    return out


class AdvisoryMonitorWorker:
    """Separate from legacy schedulers. Read-only; never places orders."""

    def __init__(self, *, interval_sec: float = 60.0) -> None:
        self.interval_sec = max(5.0, float(interval_sec))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_signals: List[AdvisorySignal] = []
        self.last_emitted: List[AdvisorySignal] = []
        self.last_run_at: Optional[str] = None
        self.running = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="r65-advisory-monitor", daemon=True)
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

        snap_obj = load_snapshot("acct_individual")
        snap = snap_obj.to_dict() if snap_obj else None
        status = robinhood_mcp_read_only_status(
            snapshot_stale=bool(snap_obj.stale) if snap_obj else None,
        )
        signals = evaluate_broker_health_signals(status, snap)
        # Optional ORATS probe flag from env/health (never auto-trade).
        orats_flag = os.environ.get("R65_ORATS_OK")
        if orats_flag is not None:
            signals.extend(evaluate_orats_health_signals(orats_ok=orats_flag.strip().lower() in {"1", "true", "yes"}))

        prev = [s.to_dict() for s in self.last_signals]
        emitted = dedupe_state_change_signals(prev, signals)
        self.last_signals = signals
        self.last_emitted = emitted
        self.last_run_at = datetime.now(timezone.utc).isoformat()
        self._persist_state()
        self._dispatch_slack(emitted if emitted else [])
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
            "emitted": [s.to_dict() for s in self.last_emitted],
            "manual_only": True,
            "trade_execution": False,
            "legacy_scheduler": False,
            "deep_link_base": public_base_url(),
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
        webhook = get_webhook_for_channel("ops") or get_webhook_for_channel("alerts") or get_webhook_for_channel("signals")
        if not webhook:
            return
        for sig in signals:
            link = sig.deep_link or build_advisory_deep_link(sig.signal_type, sig.symbol)
            text = (
                f"[ChakraOps advisory] {sig.signal_type}: {sig.message} "
                f"({sig.symbol or 'n/a'}) · as_of={sig.as_of} · manual action only · {link}"
            )
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
        "signal_types": sorted(SIGNAL_TYPES),
        "deep_link_base": public_base_url(),
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "legacy_scheduler_enabled": False,
    }
