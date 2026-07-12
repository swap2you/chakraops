# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe V2 (R36.2) builder — derive records from the latest evaluation artifact
and publish a versioned snapshot transactionally.

The builder itself makes NO provider calls: it reads the effective research pool and the
latest ``EvaluationStoreV2`` artifact (already produced by the existing evaluation) and
derives lifecycle + memberships via :mod:`policy`. Expensive evaluation/refresh remains
separate from cheap reads (which serve the published snapshot).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.universe_v2 import store
from app.core.universe_v2.model import (
    ALL_STRATEGIES,
    LIFECYCLE_ADMITTED,
    LIFECYCLE_QUARANTINE,
    LIFECYCLE_REMOVED,
    LIFECYCLE_WATCH,
    MEMBERSHIP_ELIGIBLE,
    MEMBERSHIP_NOT_ELIGIBLE,
    SCHEMA_VERSION,
    SNAPSHOT_COMPLETE,
    LifecycleTransition,
    ManualOverride,
    UniverseV2Record,
    UniverseV2Snapshot,
)
from app.core.universe_v2.policy import (
    SymbolEvalOutcome,
    derive_lifecycle,
    derive_memberships,
    resolve_reason,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _effective_and_overlay() -> Tuple[List[str], List[str], List[str], List[str]]:
    """Return (effective_symbols, base_symbols, removed_symbols, added_symbols).

    ``base_symbols`` is the CSV base pool WITHOUT overlay additions; ``added_symbols`` is the
    overlay INCLUDE set. Keeping them separate lets the builder record INCLUDE overrides.
    """
    from app.api import data_health

    base = list(data_health.get_base_universe_symbols())
    effective = list(data_health.get_universe_symbols())
    removed: List[str] = []
    added: List[str] = []
    try:
        from app.core.universe.universe_overrides import snapshot_overlay

        ov = snapshot_overlay()
        removed = [str(s).strip().upper() for s in (ov.get("removed") or [])]
        added = [str(s).strip().upper() for s in (ov.get("added") or [])]
    except Exception as e:
        logger.warning("[UNIVERSE_V2] overlay read failed: %s", e)
    return effective, base, removed, added


def _load_artifact():
    try:
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2

        st = get_evaluation_store_v2()
        st.reload_from_disk()
        return st, st.get_latest()
    except Exception as e:
        logger.warning("[UNIVERSE_V2] artifact load failed: %s", e)
        return None, None


def _regime_from_artifact(artifact) -> Optional[str]:
    if artifact is None:
        return None
    meta = getattr(artifact, "metadata", None) or {}
    for key in ("market_regime", "regime"):
        v = meta.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _market_regime_readonly() -> Optional[str]:
    """Read the last persisted market regime (``out/market/market_regime.json``) with NO
    provider call and NO recompute. This is the canonical market-wide regime that the
    decision engine already persists; unlike per-symbol diagnostics it survives artifact
    persistence/reload. Fail-closed to None if the snapshot is absent or corrupt."""
    try:
        import json

        from app.core.market.market_regime import _regime_path

        path = _regime_path()
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        regime = data.get("regime") if isinstance(data, dict) else None
        return str(regime).strip() if regime and str(regime).strip() else None
    except Exception as e:  # never let regime-read break a build
        logger.warning("[UNIVERSE_V2] market regime read failed: %s", e)
        return None


def _outcome_for_symbol(
    symbol: str,
    store_v2,
    artifact,
    removed_set,
    regime: Optional[str],
) -> SymbolEvalOutcome:
    sym = symbol.strip().upper()
    outcome = SymbolEvalOutcome(symbol=sym, is_removed=sym in removed_set, regime=regime)
    if store_v2 is None or artifact is None:
        return outcome
    got = None
    try:
        got = store_v2.get_symbol(sym)
    except Exception:
        got = None
    if not got:
        return outcome
    summary = got[0]
    outcome.has_evaluation = True
    codes = tuple(str(c) for c in (getattr(summary, "primary_reason_codes", None) or []))
    outcome.reason_codes = codes
    outcome.stage1_pass = (getattr(summary, "stage1_status", "") or "").upper() == "PASS"
    outcome.verdict = getattr(summary, "final_verdict", None) or getattr(summary, "verdict", None)
    provider_status = (getattr(summary, "provider_status", "OK") or "").strip().upper()
    # ERROR is a hard provider failure → safety-critical quarantine. WARN/None means
    # incomplete data (data_completeness < threshold) → fail-closed (not admitted/eligible),
    # but not a safety-critical quarantine.
    outcome.provider_ok = provider_status != "ERROR"
    outcome.data_complete = provider_status == "OK"
    outcome.price = getattr(summary, "price", None) or getattr(summary, "underlying_price", None)
    meta = getattr(artifact, "metadata", None) or {}
    outcome.evaluation_version = meta.get("run_id")
    outcome.as_of_utc = getattr(summary, "evaluated_at", None) or getattr(summary, "data_freshness", None)
    # Regime is a per-symbol field on the diagnostics detail (populated from the staged
    # result). Prefer it; fall back to the artifact-level regime only if per-symbol is absent.
    diagnostics = got[4] if len(got) > 4 else None
    per_symbol_regime = getattr(diagnostics, "regime", None) if diagnostics is not None else None
    if isinstance(per_symbol_regime, str) and per_symbol_regime.strip():
        outcome.regime = per_symbol_regime.strip()
    return outcome


def _update_streaks(prior: Dict[str, Any], lifecycle: str, temporary: bool) -> Tuple[int, int]:
    p = int(prior.get("pass_streak") or 0)
    f = int(prior.get("fail_streak") or 0)
    if lifecycle == LIFECYCLE_ADMITTED:
        return p + 1, 0
    if lifecycle == LIFECYCLE_QUARANTINE or (lifecycle == LIFECYCLE_WATCH and temporary):
        return 0, f + 1
    # REMOVED / WATCH-not-evaluated: neutral (preserve prior).
    return p, f


def build_universe_v2_snapshot(as_of: Optional[str] = None) -> UniverseV2Snapshot:
    """Build and publish a new versioned Universe V2 snapshot. Returns the snapshot."""
    effective, base_symbols, removed, added = _effective_and_overlay()
    removed_set = set(removed)
    added_set = set(added)
    store_v2, artifact = _load_artifact()
    # Market-wide regime resolution (read-only, survives reload): artifact metadata (future
    # artifacts may carry it) → last persisted market_regime.json (canonical). Per-symbol
    # diagnostics regime, when present in memory, refines this in _outcome_for_symbol.
    regime = _regime_from_artifact(artifact) or _market_regime_readonly()
    source_version = None
    if artifact is not None:
        source_version = (getattr(artifact, "metadata", None) or {}).get("run_id")

    state = store.load_state()
    prior_symbols: Dict[str, Any] = dict(state.get("symbols") or {})
    effective_set = set(effective)

    # Record set: effective pool ∪ removed (removed shown as REMOVED, out of pool).
    all_symbols = sorted(effective_set | removed_set)
    now = as_of or _now_iso()

    records: List[UniverseV2Record] = []
    new_symbols_state: Dict[str, Any] = {}

    for sym in all_symbols:
        outcome = _outcome_for_symbol(sym, store_v2, artifact, removed_set, regime)
        lifecycle, primary_code, safety_critical, temporary = derive_lifecycle(outcome)
        memberships = derive_memberships(outcome, lifecycle, safety_critical)

        prior = prior_symbols.get(sym, {})
        prior_state = prior.get("lifecycle_state")
        pass_streak, fail_streak = _update_streaks(prior, lifecycle, temporary)

        transitions: List[Dict[str, Any]] = list(prior.get("transitions") or [])
        last_transition = None
        if prior_state != lifecycle:
            t = LifecycleTransition(
                from_state=prior_state, to_state=lifecycle, reason_code=primary_code, at_utc=now
            )
            transitions.append(t.to_dict())
            transitions = transitions[-store.TRANSITIONS_KEEP:]
            last_transition = t
        elif transitions:
            last_transition = LifecycleTransition.from_dict(transitions[-1])

        override = None
        if sym in removed_set:
            override = ManualOverride(kind="EXCLUDE", reason="operator removal", at_utc=now)
        elif sym in added_set and sym in effective_set:
            override = ManualOverride(kind="INCLUDE", reason="operator addition", at_utc=now)

        supporting = _supporting_reasons(outcome.reason_codes, primary_code)

        rec = UniverseV2Record(
            symbol=sym,
            in_research_pool=sym in effective_set,
            lifecycle_state=lifecycle,
            memberships=memberships,
            primary_reason=resolve_reason(primary_code),
            supporting_reasons=supporting,
            safety_critical=safety_critical,
            temporary=temporary,
            pass_streak=pass_streak,
            fail_streak=fail_streak,
            last_transition=last_transition,
            evaluation_version=outcome.evaluation_version,
            data_source="ORATS" if outcome.has_evaluation else None,
            as_of_utc=outcome.as_of_utc,
            manual_override=override,
        )
        records.append(rec)

        new_symbols_state[sym] = {
            "lifecycle_state": lifecycle,
            "pass_streak": pass_streak,
            "fail_streak": fail_streak,
            "transitions": transitions,
            "override": override.to_dict() if override else None,
            "in_research_pool": sym in effective_set,
        }

    # Monotonic version: never regress even if durable state is lost/corrupt (version 0).
    # Consult both the durable state and the already-published snapshot.
    prev_state_version = int(state.get("version") or 0)
    published = store.get_latest_snapshot()
    prev_published_version = int(getattr(published, "version", 0) or 0) if published else 0
    version = max(prev_state_version, prev_published_version) + 1
    snapshot = UniverseV2Snapshot(
        version=version,
        created_at_utc=now,
        status=SNAPSHOT_COMPLETE,
        schema_version=SCHEMA_VERSION,
        source_evaluation_version=source_version,
        research_pool_count=len(effective_set),
        records=records,
        counts=_compute_counts(records),
    )

    new_state = {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "updated_at_utc": now,
        "symbols": new_symbols_state,
    }

    store.publish_snapshot(snapshot, new_state)
    logger.info("[UNIVERSE_V2] published snapshot v%d (%d records)", version, len(records))
    return snapshot


def _supporting_reasons(reason_codes, primary_code: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = {primary_code}
    for c in reason_codes:
        if c in seen:
            continue
        seen.add(c)
        out.append(resolve_reason(c))
        if len(out) >= 5:
            break
    return out


def _compute_counts(records: List[UniverseV2Record]) -> Dict[str, Any]:
    lifecycle_funnel: Dict[str, int] = {}
    strategy_eligible: Dict[str, int] = {s: 0 for s in ALL_STRATEGIES}
    strategy_not_eligible: Dict[str, int] = {s: 0 for s in ALL_STRATEGIES}
    reason_tally: Dict[str, int] = {}

    for rec in records:
        lifecycle_funnel[rec.lifecycle_state] = lifecycle_funnel.get(rec.lifecycle_state, 0) + 1
        for s, m in rec.memberships.items():
            if m.status == MEMBERSHIP_ELIGIBLE:
                strategy_eligible[s] = strategy_eligible.get(s, 0) + 1
            elif m.status == MEMBERSHIP_NOT_ELIGIBLE:
                strategy_not_eligible[s] = strategy_not_eligible.get(s, 0) + 1
        if rec.lifecycle_state in (LIFECYCLE_WATCH, LIFECYCLE_QUARANTINE) and rec.primary_reason:
            title = rec.primary_reason.get("title") or "Other"
            reason_tally[title] = reason_tally.get(title, 0) + 1

    top_reasons = sorted(reason_tally.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {
        "lifecycle_funnel": lifecycle_funnel,
        "strategy_eligible": strategy_eligible,
        "strategy_not_eligible": strategy_not_eligible,
        "top_rejection_reasons": [{"reason": r, "count": c} for r, c in top_reasons],
        "total_records": len(records),
    }
