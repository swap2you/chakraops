# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 6: Alert engine — build alerts after a run completes, dedupe, persist, deliver.
Alerts are stage-aware and actionable; Slack is only a delivery channel.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.alerts.models import Alert, AlertType, Severity

logger = logging.getLogger(__name__)

# Config path: chakraops/config/alerts.yaml
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _get_alerts_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "alerts"


def _ensure_alerts_dir() -> Path:
    path = _get_alerts_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _alerts_log_path() -> Path:
    return _ensure_alerts_dir() / "alerts_log.jsonl"


def _load_alerts_config() -> Dict[str, Any]:
    path = _repo_root() / "config" / "alerts.yaml"
    if not path.exists():
        return {
            "enabled_alert_types": ["DATA_HEALTH", "REGIME_CHANGE", "SIGNAL", "SYSTEM"],
            "cooldown_hours": 6,
            "lifecycle_cooldown_hours": 4,
            "portfolio_alert_cooldown_hours": 12,
            "slack": {},
        }
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        enabled = data.get("enabled_alert_types")
        if not isinstance(enabled, list):
            enabled = ["DATA_HEALTH", "REGIME_CHANGE", "SIGNAL", "SYSTEM"]
        slack = data.get("slack") or {}
        if not isinstance(slack.get("channels"), dict):
            slack = {**slack, "channels": {}}
        return {
            "enabled_alert_types": [str(x) for x in enabled],
            "cooldown_hours": int(data.get("cooldown_hours", 6)),
            "lifecycle_cooldown_hours": int(data.get("lifecycle_cooldown_hours", 4)),
            "portfolio_alert_cooldown_hours": int(data.get("portfolio_alert_cooldown_hours", 12)),
            "slack": slack,
        }
    except Exception as e:
        logger.warning("[ALERTS] Failed to load config %s: %s", path, e)
        return {
            "enabled_alert_types": ["DATA_HEALTH", "REGIME_CHANGE", "SIGNAL", "SYSTEM"],
            "cooldown_hours": 6,
            "lifecycle_cooldown_hours": 4,
            "slack": {},
        }


def get_previous_completed_run(current_run_id: str):  # -> Optional[EvaluationRunFull]
    """Return the most recent COMPLETED run before current_run_id (for diffing)."""
    from app.core.eval.evaluation_store import list_runs, load_run
    summaries = list_runs(limit=50)
    found_current = False
    for s in summaries:
        if s.run_id == current_run_id:
            found_current = True
            continue
        if not found_current:
            continue
        if s.status == "COMPLETED":
            run = load_run(s.run_id)
            if run:
                return run
        break
    return None


def _eligible_set(run: Any) -> set:
    if not getattr(run, "symbols", None):
        return set()
    return {s["symbol"] for s in run.symbols if isinstance(s, dict) and s.get("verdict") == "ELIGIBLE"}


def _shortlist_set(run: Any) -> set:
    candidates = getattr(run, "top_candidates", None) or []
    return {c.get("symbol") for c in candidates if isinstance(c, dict) and c.get("symbol")}


def _make_fingerprint(alert_type: str, reason_code: str, symbol: Optional[str], stage: Optional[str], extra: str = "") -> str:
    raw = f"{alert_type}|{reason_code}|{symbol or ''}|{stage or ''}|{extra}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _lifecycle_fingerprint(position_id: str, action_type: str) -> str:
    """Phase 2C: Cooldown per (position_id, action_type)."""
    raw = f"LIFECYCLE|{position_id}|{action_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _build_symbol_explain_from_run(run: Any, symbol: str) -> Dict[str, Any]:
    """Build minimal symbol_explain dict from evaluation run for lifecycle."""
    sym_upper = (symbol or "").strip().upper()
    for s in (getattr(run, "symbols", None) or []):
        if isinstance(s, dict) and (s.get("symbol") or "").strip().upper() == sym_upper:
            return {
                "symbol": sym_upper,
                "verdict": s.get("verdict", "UNKNOWN"),
                "primary_reason": s.get("primary_reason", ""),
            }
    return {"symbol": sym_upper, "verdict": "UNKNOWN", "primary_reason": ""}


def build_lifecycle_alerts_for_run(run: Any, config: Dict[str, Any]) -> List[Alert]:
    """Phase 2C: Build lifecycle alerts from OPEN/PARTIAL_EXIT positions."""
    from app.core.positions.store import list_positions
    from app.core.symbols.targets import get_targets
    from app.core.lifecycle.engine import evaluate_position_lifecycle
    from app.core.lifecycle.models import LifecycleAction

    alerts: List[Alert] = []
    now = datetime.now(timezone.utc).isoformat()
    run_id = getattr(run, "run_id", "")

    positions = list_positions(status=None)
    open_positions = [p for p in positions if (p.status or "").strip() in ("OPEN", "PARTIAL_EXIT")]
    if not open_positions:
        return alerts

    action_to_alert_type = {
        LifecycleAction.SCALE_OUT: AlertType.POSITION_SCALE_OUT,
        LifecycleAction.EXIT: AlertType.POSITION_EXIT,
        LifecycleAction.ABORT: AlertType.POSITION_ABORT,
        LifecycleAction.HOLD: AlertType.POSITION_HOLD,
    }
    action_to_severity = {
        LifecycleAction.SCALE_OUT: Severity.WARN,
        LifecycleAction.EXIT: Severity.WARN,
        LifecycleAction.ABORT: Severity.CRITICAL,
        LifecycleAction.HOLD: Severity.WARN,
    }
    # STOP_LOSS override
    for pos in open_positions:
        sym = (pos.symbol or "").strip().upper()
        symbol_explain = _build_symbol_explain_from_run(run, sym)
        symbol_targets = get_targets(sym)
        events = evaluate_position_lifecycle(pos, symbol_explain, symbol_targets, run, eval_run_id=run_id)
        for ev in events:
            at = action_to_alert_type.get(ev.action)
            if at is None:
                continue
            severity = action_to_severity.get(ev.action, Severity.WARN)
            if ev.reason and ev.reason.value == "STOP_LOSS":
                severity = Severity.CRITICAL
            fp = _lifecycle_fingerprint(pos.position_id, ev.action.value)
            meta = dict(ev.meta or {})
            meta["lifecycle_format"] = "directive"
            meta["position_id"] = pos.position_id
            meta["lifecycle_state"] = ev.lifecycle_state.value
            meta["eval_run_id"] = run_id
            if ev.action.value == "EXIT" and ev.reason and ev.reason.value == "STOP_LOSS":
                meta["reason_detail"] = "Price breached stop"
            elif ev.action.value == "EXIT":
                meta["reason_detail"] = "Target 2 hit"
            alerts.append(Alert(
                alert_type=at,
                severity=severity,
                reason_code=ev.reason.value if ev.reason else ev.action.value,
                summary=ev.directive,
                action_hint=ev.directive,
                fingerprint=fp,
                created_at=now,
                stage=None,
                symbol=sym,
                meta=meta,
            ))
    return alerts


def build_alerts_for_run(run: Any, previous_run: Optional[Any], config: Dict[str, Any]) -> List[Alert]:
    """
    Build alerts from a completed run. Dedupe rules applied later (cooldown);
    here we apply: REGIME_CHANGE only on transition, SIGNAL only when set changed.
    """
    alerts: List[Alert] = []
    now = datetime.now(timezone.utc).isoformat()
    enabled = set(config.get("enabled_alert_types") or [])

    # SYSTEM: run failed (caller should only call for COMPLETED runs; we still allow explicit FAILED handling if needed)
    if getattr(run, "status", None) == "FAILED":
        err = getattr(run, "error_summary", None) or "Run failed"
        fp = _make_fingerprint("SYSTEM", "RUN_FAILED", None, None, run.run_id)
        if "SYSTEM" in enabled:
            alerts.append(Alert(
                alert_type=AlertType.SYSTEM,
                severity=Severity.CRITICAL,
                reason_code="RUN_FAILED",
                summary=f"Evaluation run failed: {err[:100]}",
                action_hint="Check logs and data sources; re-run evaluation.",
                fingerprint=fp,
                created_at=now,
                stage=None,
                symbol=None,
                meta={"run_id": run.run_id},
            ))
        return alerts

    run_id = getattr(run, "run_id", "")
    regime = getattr(run, "regime", None) or ""
    prev_regime = (getattr(previous_run, "regime", None) or "") if previous_run else ""

    # REGIME_CHANGE: only on actual transition
    if "REGIME_CHANGE" in enabled and regime != prev_regime and (regime or prev_regime):
        fp = _make_fingerprint("REGIME_CHANGE", "REGIME_TRANSITION", None, None, f"{prev_regime}->{regime}")
        alerts.append(Alert(
            alert_type=AlertType.REGIME_CHANGE,
            severity=Severity.WARN,
            reason_code="REGIME_TRANSITION",
            summary=f"Regime changed from {prev_regime or 'N/A'} to {regime or 'N/A'}",
            action_hint="Review strategy suitability for new regime.",
            fingerprint=fp,
            created_at=now,
            stage=None,
            symbol=None,
            meta={"run_id": run_id, "prev_regime": prev_regime, "regime": regime},
        ))

    # SIGNAL: only when eligible or shortlist set changed vs previous run
    curr_eligible = _eligible_set(run)
    curr_shortlist = _shortlist_set(run)
    prev_eligible = _eligible_set(previous_run) if previous_run else set()
    prev_shortlist = _shortlist_set(previous_run) if previous_run else set()
    eligible_changed = curr_eligible != prev_eligible
    shortlist_changed = curr_shortlist != prev_shortlist
    if "SIGNAL" in enabled and (eligible_changed or shortlist_changed):
        parts = []
        if eligible_changed:
            parts.append("eligible set changed")
        if shortlist_changed:
            parts.append("shortlist changed")
        summary = f"Signal set changed: {', '.join(parts)}. Eligible: {len(curr_eligible)}, shortlist: {len(curr_shortlist)}"
        fp = _make_fingerprint("SIGNAL", "SET_CHANGE", None, None, f"{len(curr_eligible)}:{len(curr_shortlist)}")
        alerts.append(Alert(
            alert_type=AlertType.SIGNAL,
            severity=Severity.INFO,
            reason_code="SET_CHANGE",
            summary=summary,
            action_hint="Review Dashboard and History for current eligible/shortlist.",
            fingerprint=fp,
            created_at=now,
            stage=None,
            symbol=None,
            meta={"run_id": run_id, "eligible": len(curr_eligible), "shortlisted": len(curr_shortlist)},
        ))

    # DATA_HEALTH: from run errors or data quality issues (one summary alert, no per-symbol spam)
    if "DATA_HEALTH" in enabled:
        errors = getattr(run, "errors", None) or []
        err_count = len(errors)
        if err_count > 0:
            summary = f"Run had {err_count} error(s). First: {(errors[0][:80] + '...') if len(errors[0]) > 80 else errors[0]}"
            fp = _make_fingerprint("DATA_HEALTH", "RUN_ERRORS", None, None, str(err_count))
            alerts.append(Alert(
                alert_type=AlertType.DATA_HEALTH,
                severity=Severity.WARN if err_count <= 3 else Severity.CRITICAL,
                reason_code="RUN_ERRORS",
                summary=summary,
                action_hint="Check symbol diagnostics and data sources.",
                fingerprint=fp,
                created_at=now,
                stage=None,
                symbol=None,
                meta={"run_id": run_id, "errors_count": err_count},
            ))
        # Optional: low data completeness across run (single aggregate alert)
        symbols = getattr(run, "symbols", None) or []
        if symbols:
            incomplete = [s for s in symbols if isinstance(s, dict) and (s.get("data_completeness") or 1.0) < 0.9]
            if len(incomplete) > len(symbols) // 2:
                fp = _make_fingerprint("DATA_HEALTH", "LOW_COMPLETENESS", None, None, str(len(incomplete)))
                alerts.append(Alert(
                    alert_type=AlertType.DATA_HEALTH,
                    severity=Severity.WARN,
                    reason_code="LOW_COMPLETENESS",
                    summary=f"{len(incomplete)}/{len(symbols)} symbols have low data completeness",
                    action_hint="Check data pipeline and ORATS/quote availability.",
                    fingerprint=fp,
                    created_at=now,
                    stage=None,
                    symbol=None,
                    meta={"run_id": run_id, "incomplete": len(incomplete), "total": len(symbols)},
                ))

    return alerts


def _get_recent_sent_fingerprints(cooldown_seconds: int) -> set:
    path = _alerts_log_path()
    if not path.exists():
        return set()
    cutoff = datetime.now(timezone.utc).timestamp() - cooldown_seconds
    seen = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("sent") and rec.get("sent_at"):
                        ts_str = rec["sent_at"]
                        try:
                            # ISO format
                            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if dt.timestamp() >= cutoff:
                                seen.add(rec.get("fingerprint") or "")
                        except Exception:
                            pass
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning("[ALERTS] Failed to read log for dedupe: %s", e)
    return seen


def _append_alert_record(record: Dict[str, Any]) -> None:
    path = _alerts_log_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    # Phase 8.3: Append DATA_HEALTH alerts to notifications (UI parity with Slack)
    if record.get("alert_type") == "DATA_HEALTH":
        try:
            from app.api.notifications_store import append_notification
            append_notification(
                record.get("severity", "WARN"),
                "DATA_HEALTH",
                record.get("summary", "Data health alert"),
                details={"action_hint": record.get("action_hint")},
            )
        except Exception as e:
            logger.debug("[ALERTS] Failed to append DATA_HEALTH to notifications: %s", e)


def _append_lifecycle_log_if_lifecycle(alert: Alert, sent: bool) -> None:
    """Phase 2C: Append to lifecycle_log.jsonl for lifecycle alerts."""
    meta = alert.meta or {}
    if meta.get("lifecycle_format") != "directive":
        return
    try:
        from app.core.lifecycle.persistence import append_lifecycle_entry
        append_lifecycle_entry({
            "position_id": meta.get("position_id", ""),
            "symbol": alert.symbol or "",
            "lifecycle_state": meta.get("lifecycle_state", ""),
            "action": alert.alert_type.value,
            "reason": alert.reason_code,
            "directive": alert.action_hint or alert.summary,
            "triggered_at": alert.created_at,
            "eval_run_id": meta.get("eval_run_id", ""),
            "sent": sent,
        })
    except Exception as e:
        logger.warning("[ALERTS] Failed to append lifecycle log: %s", e)


def process_run_completed(run: Any) -> None:
    """
    Called after a run is saved and (if COMPLETED) latest pointer updated.
    Builds alerts (evaluation + lifecycle), dedupes by fingerprint cooldown,
    sends via Slack (if configured), persists to out/alerts/ and out/lifecycle/.
    No alerts during RUNNING; no per-symbol spam.
    """
    if getattr(run, "status", None) == "RUNNING":
        return
    config = _load_alerts_config()
    enabled = set(config.get("enabled_alert_types") or [])
    cooldown_hours = max(0, config.get("cooldown_hours", 6))
    cooldown_seconds = cooldown_hours * 3600
    lifecycle_cooldown_hours = max(0, config.get("lifecycle_cooldown_hours", 4))
    lifecycle_cooldown_seconds = lifecycle_cooldown_hours * 3600
    portfolio_cooldown_hours = max(0, config.get("portfolio_alert_cooldown_hours", 12))
    portfolio_cooldown_seconds = portfolio_cooldown_hours * 3600

    previous_run = get_previous_completed_run(run.run_id) if getattr(run, "run_id", None) else None
    candidates = build_alerts_for_run(run, previous_run, config)
    recent_fps = _get_recent_sent_fingerprints(cooldown_seconds)
    recent_lifecycle_fps = _get_recent_sent_fingerprints(lifecycle_cooldown_seconds)
    recent_portfolio_fps = _get_recent_sent_fingerprints(portfolio_cooldown_seconds)

    # Phase 2C: Lifecycle alerts for OPEN/PARTIAL_EXIT positions
    lifecycle_alerts = build_lifecycle_alerts_for_run(run, config)
    candidates = candidates + lifecycle_alerts

    # Phase 3: Portfolio risk alerts
    try:
        from app.core.portfolio.service import compute_portfolio_summary
        from app.core.accounts.store import list_accounts
        from app.core.positions.store import list_positions
        from app.core.alerts.portfolio_alerts import build_portfolio_alerts_for_run

        accounts = list_accounts()
        positions = list_positions()
        summary = compute_portfolio_summary(accounts, positions)
        portfolio_alerts = build_portfolio_alerts_for_run(summary, summary.risk_flags, config)
        candidates = candidates + portfolio_alerts
    except Exception as e:
        logger.debug("[ALERTS] Portfolio alerts skipped: %s", e)

    from app.core.alerts.slack_notifier import SlackNotifier
    notifier = SlackNotifier(config)

    lifecycle_types = {"POSITION_ENTRY", "POSITION_SCALE_OUT", "POSITION_EXIT", "POSITION_ABORT", "POSITION_HOLD"}
    portfolio_types = {"PORTFOLIO_RISK_WARN", "PORTFOLIO_RISK_BLOCK"}

    for alert in candidates:
        if alert.alert_type.value not in enabled:
            _append_alert_record({
                "fingerprint": alert.fingerprint,
                "created_at": alert.created_at,
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "summary": alert.summary,
                "action_hint": alert.action_hint,
                "sent": False,
                "suppressed_reason": "alert_type_disabled",
            })
            if alert.alert_type.value in lifecycle_types:
                _append_lifecycle_log_if_lifecycle(alert, sent=False)
            continue
        fps_to_check = (
            recent_lifecycle_fps if alert.alert_type.value in lifecycle_types
            else recent_portfolio_fps if alert.alert_type.value in portfolio_types
            else recent_fps
        )
        if alert.fingerprint in fps_to_check:
            _append_alert_record({
                "fingerprint": alert.fingerprint,
                "created_at": alert.created_at,
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "summary": alert.summary,
                "action_hint": alert.action_hint,
                "sent": False,
                "suppressed_reason": "cooldown",
            })
            if alert.alert_type.value in lifecycle_types:
                _append_lifecycle_log_if_lifecycle(alert, sent=False)
            logger.debug("[ALERTS] Suppressed (cooldown) fingerprint=%s", alert.fingerprint[:8])
            continue
        sent = notifier.send(alert)
        (recent_lifecycle_fps if alert.alert_type.value in lifecycle_types
         else recent_portfolio_fps if alert.alert_type.value in portfolio_types
         else recent_fps).add(alert.fingerprint)
        if alert.alert_type.value in lifecycle_types:
            _append_lifecycle_log_if_lifecycle(alert, sent=sent)
        _append_alert_record({
            "fingerprint": alert.fingerprint,
            "created_at": alert.created_at,
            "alert_type": alert.alert_type.value,
            "severity": alert.severity.value,
            "summary": alert.summary,
            "action_hint": alert.action_hint,
            "sent": sent,
            "sent_at": datetime.now(timezone.utc).isoformat() if sent else None,
            "suppressed_reason": None if sent else "slack_not_configured",
        })


def list_recent_alert_records(limit: int = 100) -> List[Dict[str, Any]]:
    """Return most recent alert log records (for API/UI). Newest first."""
    path = _alerts_log_path()
    if not path.exists():
        return []
    lines = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception as e:
        logger.warning("[ALERTS] Failed to read log: %s", e)
        return []
    result = []
    for line in reversed(lines[-limit:]):
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result[:limit]


def get_alerting_status() -> Dict[str, Any]:
    """Slack configured? Used by UI to show 'alerts suppressed (Slack not configured)'."""
    default_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    config = _load_alerts_config()
    slack_cfg = config.get("slack") or {}
    channels = slack_cfg.get("channels") or {}
    # If any type has an explicit webhook, we consider Slack configured for that path
    has_any = bool(default_url)
    return {
        "slack_configured": has_any,
        "message": "Slack not configured" if not has_any else "Slack webhook configured",
    }
