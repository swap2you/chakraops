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

# R70.1: durable notification delivery state (successful sends only).
_PROCESSED_NOTIFICATION_RUN_IDS: set[str] = set()  # legacy in-memory mirror for tests
_PROCESSED_ALERT_IDENTITIES: set[str] = set()
_DELIVERY_STATE_LOCK = __import__("threading").Lock()
_MAX_DELIVERY_RUNS = 200


def _notification_delivery_path() -> Path:
    return _get_alerts_dir() / "notification_delivery_state.json"


def _load_delivery_state() -> Dict[str, Any]:
    path = _notification_delivery_path()
    if not path.exists():
        return {"runs": {}, "order": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"runs": {}, "order": []}
        data.setdefault("runs", {})
        data.setdefault("order", [])
        return data
    except Exception as e:
        logger.debug("[ALERTS] delivery state load failed: %s", e)
        return {"runs": {}, "order": []}


def _atomic_write_delivery_state(data: Dict[str, Any]) -> None:
    path = _notification_delivery_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from app.core.io.atomic import atomic_write_json

        atomic_write_json(path, data, indent=0)
    except Exception:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0)
        tmp.replace(path)


def _prune_delivery_state(data: Dict[str, Any]) -> None:
    order = list(data.get("order") or [])
    runs = data.get("runs") or {}
    # Chronological prune: drop oldest run entries beyond bound.
    while len(order) > _MAX_DELIVERY_RUNS:
        old = order.pop(0)
        runs.pop(old, None)
    data["order"] = order
    data["runs"] = runs


def _delivery_mark(run_id: str, item_key: str, *, status: str, channel: Optional[str] = None) -> None:
    if not run_id or not item_key:
        return
    with _DELIVERY_STATE_LOCK:
        data = _load_delivery_state()
        runs = data.setdefault("runs", {})
        order = data.setdefault("order", [])
        if run_id not in runs:
            runs[run_id] = {"items": {}}
            order.append(run_id)
        items = runs[run_id].setdefault("items", {})
        items[item_key] = {
            "status": status,
            "channel": channel,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        _prune_delivery_state(data)
        _atomic_write_delivery_state(data)
        if status == "sent":
            if item_key == "EVAL_SUMMARY":
                _PROCESSED_NOTIFICATION_RUN_IDS.add(run_id)
            else:
                _PROCESSED_ALERT_IDENTITIES.add(f"{run_id}:{item_key}")


def _delivery_was_sent(run_id: str, item_key: str) -> bool:
    if not run_id or not item_key:
        return False
    with _DELIVERY_STATE_LOCK:
        data = _load_delivery_state()
        items = ((data.get("runs") or {}).get(run_id) or {}).get("items") or {}
        rec = items.get(item_key) or {}
        return str(rec.get("status") or "") == "sent"


def clear_notification_idempotency_state() -> None:
    """Test helper: reset in-memory and durable notification dedupe state.

    Fail-closed: refuses to wipe canonical production delivery state unless an
    explicit test-only guard is active after an isolated alerts/OUT_DIR inject.
    """
    import os

    global _PROCESSED_NOTIFICATION_RUN_IDS, _PROCESSED_ALERT_IDENTITIES
    alerts_dir = _get_alerts_dir().resolve()
    guard = (os.environ.get("CHAKRAOPS_ALLOW_CLEAR_NOTIFICATION_STATE") or "").strip() == "1"
    path_norm = str(alerts_dir).replace("\\", "/").lower()
    looks_canonical = path_norm.endswith("/out/alerts") or path_norm.endswith("\\out\\alerts")
    try:
        from app.core.settings import get_output_dir

        # Compare against current get_output_dir (may already be monkeypatched in tests).
        current_out_alerts = (Path(get_output_dir()).resolve() / "alerts")
        if alerts_dir == current_out_alerts and "out/alerts" in path_norm:
            # Still require guard — never clear "out/alerts" without it.
            looks_canonical = True
    except Exception:
        pass
    if looks_canonical and not guard:
        raise RuntimeError(
            "Refusing to clear canonical notification_delivery_state.json without "
            "test isolation (inject isolated OUT_DIR/alerts and set "
            "CHAKRAOPS_ALLOW_CLEAR_NOTIFICATION_STATE=1)."
        )
    if not guard:
        # Secondary: also refuse non-temp paths without the guard.
        import tempfile

        temp_root = str(Path(tempfile.gettempdir()).resolve()).lower().replace("\\", "/")
        resolved = path_norm
        under_temp = resolved.startswith(temp_root) or "/pytest" in resolved
        if not under_temp:
            raise RuntimeError(
                "Refusing to clear notification_delivery_state.json without "
                "CHAKRAOPS_ALLOW_CLEAR_NOTIFICATION_STATE=1 and an isolated alerts dir."
            )
    _PROCESSED_NOTIFICATION_RUN_IDS = set()
    _PROCESSED_ALERT_IDENTITIES = set()
    with _DELIVERY_STATE_LOCK:
        try:
            path = _notification_delivery_path()
            if path.exists():
                path.unlink()
        except Exception:
            pass
        _atomic_write_delivery_state({"runs": {}, "order": []})


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


def _sorted_identity_key(symbols: set) -> str:
    return ",".join(sorted(str(s).strip().upper() for s in symbols if s))


def _top_qualified_candidates(run: Any, *, limit: int = 3) -> List[Dict[str, Any]]:
    """Top qualified candidates from ledger top_candidates / eligible symbols (artifact-derived)."""
    out: List[Dict[str, Any]] = []
    seen = set()
    sources: List[tuple[str, list]] = [
        ("top", list(getattr(run, "top_candidates", None) or [])),
        ("symbols", list(getattr(run, "symbols", None) or [])),
    ]
    for source_name, rows in sources:
        for row in rows:
            if not isinstance(row, dict):
                continue
            verd = str(row.get("verdict") or "").strip().upper()
            if source_name == "symbols" and verd not in ("ELIGIBLE", "SHORTLISTED", ""):
                continue
            if source_name == "symbols" and verd == "":
                continue
            if source_name == "symbols" and verd not in ("ELIGIBLE", "SHORTLISTED"):
                continue
            sym = (row.get("symbol") or "").strip().upper()
            if not sym or sym in seen:
                continue
            trades = row.get("candidate_trades") or []
            first = trades[0] if trades and isinstance(trades[0], dict) else {}
            reasons = []
            if row.get("primary_reason"):
                reasons.append(str(row.get("primary_reason")))
            why = first.get("why_this_trade") if isinstance(first, dict) else None
            if why:
                reasons.append(str(why))
            qty = row.get("quantity")
            if qty is None:
                qty = first.get("quantity")
            sug = first.get("suggested_quantity") or row.get("suggested_quantity")
            detail = {
                "symbol": sym,
                "verdict": verd or "ELIGIBLE",
                "strategy": row.get("strategy") or first.get("strategy") or "CSP",
                "score": row.get("score"),
                "band": row.get("band"),
                "primary_reason": row.get("primary_reason"),
                "expiration": (
                    row.get("selected_expiration")
                    or row.get("expiration")
                    or first.get("expiration")
                    or first.get("expiry")
                ),
                "strike": row.get("selected_strike")
                if row.get("selected_strike") is not None
                else first.get("strike"),
                "right": first.get("right") or first.get("option_type") or "P",
                "quantity": qty,
                "suggested_quantity": sug if sug is not None else (1 if qty is None else None),
                "quantity_label": "suggested quantity" if qty is None else "quantity",
                "contract_key": row.get("selected_contract_key")
                or first.get("contract_key")
                or first.get("option_symbol"),
                "reasons": reasons[:3],
            }
            out.append(detail)
            seen.add(sym)
            if len(out) >= limit:
                return out
    return out


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
            # Expanded Slack position fields (journal-tracked; never claim LIVE broker open
            # unless broker confirmation meta is explicitly present).
            meta.setdefault("account_alias", getattr(pos, "account_id", None) or "manual")
            meta.setdefault("broker_source", "manual_journal")
            meta.setdefault("broker_state", "manual journal — not a LIVE Robinhood open")
            meta["live_confirmed"] = False
            try:
                from app.core.portfolio.capital_authority_r70 import (
                    STATE_FRESH,
                    get_broker_freshness_view,
                    symbol_has_broker_conflict,
                )

                bv = get_broker_freshness_view("acct_individual")
                meta["broker_freshness"] = bv.get("state")
                meta["broker_as_of"] = bv.get("as_of")
                meta["snapshot_age"] = bv.get("age_minutes")
                # Effective age-based state only — never display raw snap freshness=fresh when STALE.
                meta["freshness"] = bv.get("state")
                conflict = symbol_has_broker_conflict(sym, freshness=bv)
                if bv.get("state") == STATE_FRESH and conflict is True:
                    meta["live_confirmed"] = True
                    meta["broker_source"] = bv.get("source") or "robinhood_mcp"
                    meta["broker_state"] = "Robinhood confirmed LIVE"
                    meta["account_alias"] = bv.get("account_alias") or meta["account_alias"]
                elif bv.get("state") == STATE_FRESH:
                    meta["broker_state"] = "advisory — journal row not confirmed on fresh broker snapshot"
                else:
                    meta["broker_state"] = (
                        f"advisory/unverified — broker {bv.get('state')}; refresh required"
                    )
            except Exception:
                pass
            meta.setdefault("strategy", getattr(pos, "strategy", None))
            meta.setdefault("expiration", getattr(pos, "expiration", None))
            meta.setdefault("strike", getattr(pos, "strike", None))
            meta.setdefault("right", getattr(pos, "option_type", None))
            meta.setdefault(
                "quantity",
                getattr(pos, "contracts", None) or getattr(pos, "quantity", None),
            )
            meta.setdefault(
                "contract_key",
                getattr(pos, "contract_key", None) or getattr(pos, "option_symbol", None),
            )
            if getattr(pos, "strike", None) is not None and getattr(pos, "expiration", None):
                right = (getattr(pos, "option_type", None) or "?").upper()[:1] or "?"
                meta.setdefault(
                    "contract_detail",
                    f"{pos.symbol} {pos.expiration} {right} {pos.strike}",
                )
            meta.setdefault("entry_credit", getattr(pos, "open_credit", None) or getattr(pos, "credit_expected", None))
            meta.setdefault("cost_basis", getattr(pos, "open_price", None))
            meta.setdefault("mark", getattr(pos, "mark_price_per_contract", None))
            meta.setdefault("mark_ts", getattr(pos, "mark_time_utc", None))
            try:
                from app.core.positions.lifecycle import compute_dte

                meta.setdefault("dte", compute_dte(getattr(pos, "expiration", None)))
            except Exception:
                pass
            meta.setdefault("recommendation", ev.directive)
            if ev.action.value == "EXIT" and ev.reason and ev.reason.value == "STOP_LOSS":
                meta["reason_detail"] = "Price breached stop"
            elif ev.action.value == "EXIT":
                meta["reason_detail"] = "Target 2 hit"
            reasons = []
            if ev.reason:
                reasons.append(str(ev.reason.value))
            if meta.get("reason_detail"):
                reasons.append(str(meta["reason_detail"]))
            meta.setdefault("reasons", reasons[:2])
            meta.setdefault("trigger", ev.reason.value if ev.reason else ev.action.value)
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
        top_cands = _top_qualified_candidates(run, limit=3)
        identity = _sorted_identity_key(curr_eligible) or _sorted_identity_key(curr_shortlist)
        # Fingerprint must incorporate sorted symbol/candidate identity, not only counts.
        fp = _make_fingerprint(
            "SIGNAL",
            "SET_CHANGE",
            None,
            None,
            f"elig={identity}|sl={_sorted_identity_key(curr_shortlist)}",
        )
        primary = top_cands[0] if top_cands else None
        if primary:
            summary = (
                f"Qualified setup: {primary.get('symbol')} "
                f"{primary.get('strategy') or 'CSP'} "
                f"score={primary.get('score')} band={primary.get('band')}. "
                f"{', '.join(parts)}. Eligible: {len(curr_eligible)}"
            )
            action_hint = (
                f"Review {primary.get('symbol')} "
                f"{primary.get('expiration') or ''} "
                f"{primary.get('right') or ''} "
                f"{primary.get('strike') if primary.get('strike') is not None else ''} "
                f"— MANUAL ONLY — NO ORDER SENT"
            )
        else:
            summary = (
                f"Signal set changed: {', '.join(parts)}. "
                f"Eligible: {len(curr_eligible)}, shortlist: {len(curr_shortlist)}"
            )
            action_hint = "Review Dashboard and History for current eligible/shortlist."

        broker_meta: Dict[str, Any] = {
            "run_id": run_id,
            "eligible": len(curr_eligible),
            "shortlisted": len(curr_shortlist),
            "eligible_symbols": sorted(curr_eligible),
            "candidates": top_cands,
            "manual_only": True,
            "trade_execution": False,
            "actionability": "MANUAL ONLY — NO ORDER SENT",
        }
        if primary:
            broker_meta.update(
                {
                    "strategy": primary.get("strategy"),
                    "score": primary.get("score"),
                    "band": primary.get("band"),
                    "expiration": primary.get("expiration"),
                    "strike": primary.get("strike"),
                    "right": primary.get("right"),
                    "quantity": primary.get("quantity"),
                    "suggested_quantity": primary.get("suggested_quantity"),
                    "quantity_label": primary.get("quantity_label"),
                    "contract_key": primary.get("contract_key"),
                    "contract_detail": (
                        f"{primary.get('symbol')} {primary.get('expiration') or ''} "
                        f"{primary.get('right') or ''} {primary.get('strike') if primary.get('strike') is not None else ''}"
                    ).strip(),
                    "reasons": primary.get("reasons") or [],
                    "primary_reason": primary.get("primary_reason"),
                }
            )
        try:
            from app.core.portfolio.capital_authority_r70 import (
                STATE_FRESH,
                get_broker_freshness_view,
                robinhood_conflict_check_label,
                symbol_has_broker_conflict,
            )

            bv = get_broker_freshness_view("acct_individual")
            fres_state = str(bv.get("state") or "UNAVAILABLE")
            broker_meta.update(
                {
                    "broker_freshness": fres_state,
                    "freshness_state": fres_state,
                    "broker_as_of": bv.get("as_of"),
                    "broker_age_minutes": bv.get("age_minutes"),
                    "account_alias": bv.get("account_alias"),
                    "sizing_blocked": bool(bv.get("sizing_blocked", True)),
                    "orats_actionability": "see daily summary",
                }
            )
            # Per-candidate conflict checks; aggregate never CLEAR unless all checked.
            cand_conflicts: List[Dict[str, Any]] = []
            checked_values: List[Optional[bool]] = []
            for c in top_cands:
                c_sym = c.get("symbol")
                c_conflict = symbol_has_broker_conflict(c_sym, freshness=bv)
                checked_values.append(c_conflict)
                c_label = robinhood_conflict_check_label(fres_state, conflict=c_conflict, aggregate=False)
                c["robinhood_conflict"] = c_conflict
                c["robinhood_conflict_label"] = c_label
                cand_conflicts.append(
                    {"symbol": c_sym, "conflict": c_conflict, "label": c_label}
                )
            broker_meta["candidate_conflicts"] = cand_conflicts
            if not top_cands:
                # Aggregate SIGNAL with no symbol: never CLEAR.
                _ = symbol_has_broker_conflict(None, freshness=bv)  # must be None
                broker_meta["robinhood_conflict"] = None
                broker_meta["robinhood_conflict_label"] = (
                    "Conflict check: NOT PERFORMED — no symbol supplied"
                )
            else:
                all_checked = fres_state == STATE_FRESH and all(v is not None for v in checked_values)
                any_conflict = any(v is True for v in checked_values)
                all_clear = all_checked and all(v is False for v in checked_values)
                agg_conflict: Optional[bool]
                if any_conflict:
                    agg_conflict = True
                elif all_clear:
                    agg_conflict = False
                else:
                    agg_conflict = None
                broker_meta["robinhood_conflict"] = agg_conflict
                if all_clear:
                    broker_meta["robinhood_conflict_label"] = robinhood_conflict_check_label(
                        fres_state,
                        conflict=False,
                        aggregate=True,
                        checked_all=True,
                    )
                elif any_conflict and all_checked:
                    broker_meta["robinhood_conflict_label"] = robinhood_conflict_check_label(
                        fres_state,
                        conflict=True,
                        aggregate=True,
                        checked_all=True,
                    )
                else:
                    broker_meta["robinhood_conflict_label"] = (
                        "Conflict check: PARTIAL — see candidate details"
                    )
        except Exception as e:
            logger.debug("[ALERTS] SIGNAL broker context skipped: %s", e)
            broker_meta["broker_freshness"] = "UNAVAILABLE"
            broker_meta["robinhood_conflict"] = None
            broker_meta["robinhood_conflict_label"] = (
                "Conflict check: NOT PERFORMED — no symbol supplied"
            )
        alerts.append(Alert(
            alert_type=AlertType.SIGNAL,
            severity=Severity.INFO,
            reason_code="SET_CHANGE",
            summary=summary,
            action_hint=action_hint,
            fingerprint=fp,
            created_at=now,
            stage=None,
            # Keep symbol=None for aggregate SIGNAL; details live in meta.candidates.
            symbol=None,
            meta=broker_meta,
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
                subtype=record.get("reason_code"),
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

    Idempotency: successful (run_id, alert identity) deliveries are durable and
    not duplicated. Failed deliveries remain retryable. EVAL_SUMMARY only for COMPLETED.
    """
    if getattr(run, "status", None) == "RUNNING":
        return

    run_id = str(getattr(run, "run_id", "") or "").strip()

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

    status_u = str(getattr(run, "status", "") or "").strip().upper()
    # Failed LIVE: at most one SYSTEM/DATA_HEALTH failure notify — no lifecycle,
    # portfolio, success summary, or trading SIGNAL (SIGNAL already omitted by builder).
    if status_u in ("FAILED", "ABANDONED"):
        lifecycle_alerts = []
    else:
        # Phase 2C: Lifecycle alerts for OPEN/PARTIAL_EXIT positions
        lifecycle_alerts = build_lifecycle_alerts_for_run(run, config)
    candidates = candidates + lifecycle_alerts

    # Phase 3: Portfolio risk alerts (COMPLETED only)
    if status_u == "COMPLETED":
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

    sent_by_channel: Dict[str, int] = {}

    for alert in candidates:
        identity_key = f"{run_id}:{alert.fingerprint}" if run_id else alert.fingerprint
        # Durable success: skip only previously successful deliveries.
        if run_id and _delivery_was_sent(run_id, alert.fingerprint):
            _append_alert_record({
                "fingerprint": alert.fingerprint,
                "created_at": alert.created_at,
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "summary": alert.summary,
                "action_hint": alert.action_hint,
                "reason_code": alert.reason_code,
                "sent": False,
                "suppressed_reason": "already_sent_durable",
            })
            continue
        if identity_key in _PROCESSED_ALERT_IDENTITIES and _delivery_was_sent(run_id, alert.fingerprint):
            continue
        if alert.alert_type.value not in enabled:
            _append_alert_record({
                "fingerprint": alert.fingerprint,
                "created_at": alert.created_at,
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "summary": alert.summary,
                "action_hint": alert.action_hint,
                "reason_code": alert.reason_code,
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
                "reason_code": alert.reason_code,
                "sent": False,
                "suppressed_reason": "cooldown",
            })
            if alert.alert_type.value in lifecycle_types:
                _append_lifecycle_log_if_lifecycle(alert, sent=False)
            logger.debug("[ALERTS] Suppressed (cooldown) fingerprint=%s", alert.fingerprint[:8])
            continue
        sent = False
        try:
            sent = notifier.send(alert)
        except Exception as send_exc:
            logger.warning("[ALERTS] Slack send exception (non-fatal): %s", send_exc)
            sent = False
        ch = notifier._channel_for_alert(alert)
        if sent:
            _delivery_mark(run_id, alert.fingerprint, status="sent", channel=ch)
            sent_by_channel[ch] = sent_by_channel.get(ch, 0) + 1
            fps_to_check.add(alert.fingerprint)
        else:
            _delivery_mark(run_id, alert.fingerprint, status="failed", channel=ch)
        if alert.alert_type.value in lifecycle_types:
            _append_lifecycle_log_if_lifecycle(alert, sent=sent)
        _append_alert_record({
            "fingerprint": alert.fingerprint,
            "created_at": alert.created_at,
            "alert_type": alert.alert_type.value,
            "severity": alert.severity.value,
            "summary": alert.summary,
            "action_hint": alert.action_hint,
            "reason_code": alert.reason_code,
            "sent": sent,
            "sent_at": datetime.now(timezone.utc).isoformat() if sent else None,
            "suppressed_reason": None if sent else "slack_not_configured_or_failed",
        })

    # R21.5.2 / R70.1: EVAL_SUMMARY only for successful COMPLETED runs
    try:
        status = str(getattr(run, "status", "") or "").strip().upper()
        if status != "COMPLETED":
            logger.info("[ALERTS] Skipping EVAL_SUMMARY for non-COMPLETED status=%s run_id=%s", status, run_id)
            return
        from app.core.alerts.eval_summary import (
            build_eval_summary_payload,
            should_send_eval_summary_this_run,
        )
        if run_id and _delivery_was_sent(run_id, "EVAL_SUMMARY"):
            logger.info("[ALERTS] EVAL_SUMMARY already sent for run_id=%s (durable)", run_id)
            return
        if should_send_eval_summary_this_run(run_id or ""):
            duration_sec = getattr(run, "duration_seconds", None)
            duration_ms = (duration_sec * 1000) if duration_sec is not None else None
            payload = build_eval_summary_payload(
                run,
                sent_by_channel=sent_by_channel or None,
                duration_ms=duration_ms,
                last_run_ok=True,
            )
            try:
                ok = notifier.send_eval_summary("daily", payload)
                if ok:
                    _delivery_mark(run_id, "EVAL_SUMMARY", status="sent", channel="daily")
                else:
                    _delivery_mark(run_id, "EVAL_SUMMARY", status="failed", channel="daily")
            except Exception as e:
                logger.warning("[ALERTS] Eval summary send failed (non-fatal): %s", e)
                _delivery_mark(run_id, "EVAL_SUMMARY", status="failed", channel="daily")
    except Exception as e:
        logger.warning("[ALERTS] Eval summary send failed (non-fatal): %s", e)


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
