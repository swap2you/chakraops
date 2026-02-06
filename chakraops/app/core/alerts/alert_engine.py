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
            "slack": slack,
        }
    except Exception as e:
        logger.warning("[ALERTS] Failed to load config %s: %s", path, e)
        return {
            "enabled_alert_types": ["DATA_HEALTH", "REGIME_CHANGE", "SIGNAL", "SYSTEM"],
            "cooldown_hours": 6,
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


def process_run_completed(run: Any) -> None:
    """
    Called after a run is saved and (if COMPLETED) latest pointer updated.
    Builds alerts, dedupes by fingerprint cooldown, sends via Slack (if configured), persists to out/alerts/.
    No alerts during RUNNING; no per-symbol spam.
    """
    if getattr(run, "status", None) == "RUNNING":
        return
    config = _load_alerts_config()
    enabled = set(config.get("enabled_alert_types") or [])
    cooldown_hours = max(0, config.get("cooldown_hours", 6))
    cooldown_seconds = cooldown_hours * 3600

    previous_run = get_previous_completed_run(run.run_id) if getattr(run, "run_id", None) else None
    candidates = build_alerts_for_run(run, previous_run, config)
    recent_fps = _get_recent_sent_fingerprints(cooldown_seconds)

    from app.core.alerts.slack_notifier import SlackNotifier
    notifier = SlackNotifier(config)

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
            continue
        if alert.fingerprint in recent_fps:
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
            logger.debug("[ALERTS] Suppressed (cooldown) fingerprint=%s", alert.fingerprint[:8])
            continue
        sent = notifier.send(alert)
        recent_fps.add(alert.fingerprint)
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
