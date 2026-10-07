# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Config freeze guard for live discipline (Phase 6.1).

Hashes critical configs (strategy thresholds, risk limits, gates). On startup,
compares hash with last run. If changed while run_mode != DRY_RUN, blocks
execution and explains (changed keys).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.persistence import get_config_freeze_state, save_config_freeze_state
from app.core.run_mode import RunMode
from app.core.settings import (
    get_confidence_config,
    get_environment_config,
    get_options_context_config,
    get_portfolio_config,
    get_volatility_config,
)

logger = logging.getLogger(__name__)


@dataclass
class FreezeResult:
    """Result of freeze check: allowed, message, changed keys, config_frozen."""

    allowed: bool
    message: str
    changed_keys: List[str]
    config_frozen: bool


def _env_for_freeze(env: Dict[str, Any]) -> Dict[str, Any]:
    """Make environment config JSON-serializable (risk_posture -> value)."""
    out = dict(env)
    rp = out.get("risk_posture")
    if rp is not None and hasattr(rp, "value"):
        out["risk_posture"] = rp.value
    return out


def build_critical_config_snapshot() -> Dict[str, Any]:
    """Build a canonical snapshot of critical config (strategy thresholds, risk limits, gates).

    Must stay in sync with configs used in scripts/run_and_save.py for engine and gates.
    """
    vol = get_volatility_config()
    conf = get_confidence_config()
    port = get_portfolio_config()
    env = get_environment_config()
    opts_ctx = get_options_context_config()

    # Scoring/selection/context_gate as built in run_and_save (same keys and sources)
    scoring = {
        "premium_weight": 0.50,
        "dte_weight": 0.25,
        "liquidity_weight": 0.25,
        "spread_weight": 0.0,
        "otm_weight": 0.0,
        "context_weight": 0.0,
        "strategy_preference_weight": opts_ctx.get("strategy_preference_weight", 0.15),
        "strategy_iv_rank_high_pct": opts_ctx.get("strategy_iv_rank_high_pct", 60.0),
        "strategy_iv_rank_low_pct": opts_ctx.get("strategy_iv_rank_low_pct", 20.0),
        "strategy_term_slope_backwardation_min": opts_ctx.get("strategy_term_slope_backwardation_min", 0.0),
        "strategy_term_slope_contango_max": opts_ctx.get("strategy_term_slope_contango_max", 0.0),
    }
    context_gate = {
        "iv_rank_min_sell_pct": opts_ctx.get("iv_rank_min_sell_pct", 10.0),
        "iv_rank_max_sell_pct": opts_ctx.get("iv_rank_max_sell_pct", 90.0),
        "iv_rank_max_buy_pct": opts_ctx.get("iv_rank_max_buy_pct", 70.0),
        "dte_event_window": opts_ctx.get("dte_event_window", 7),
        "expected_move_gate": opts_ctx.get("expected_move_gate", True),
    }
    selection = {
        "max_total": 10,
        "max_per_symbol": 2,
        "max_per_signal_type": None,
        "min_score": 0.0,
        "min_confidence_threshold": conf.get("min_confidence_threshold", 40),
        "context_gate": context_gate,
    }
    signal_engine_base = {
        "dte_min": 7,
        "dte_max": 45,
        "min_bid": 0.01,
        "min_open_interest": 50,
        "max_spread_pct": 25.0,
    }

    return {
        "volatility": vol,
        "confidence": conf,
        "portfolio": port,
        "environment": _env_for_freeze(env),
        "options_context": opts_ctx,
        "scoring": scoring,
        "context_gate": context_gate,
        "selection": selection,
        "signal_engine_base": signal_engine_base,
    }


def _canonical_json(obj: Any) -> str:
    """Serialize to deterministic JSON (sorted keys)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def hash_snapshot(snapshot: Dict[str, Any]) -> str:
    """Compute deterministic hash of critical config snapshot."""
    payload = _canonical_json(snapshot)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _changed_keys(current: Dict[str, Any], previous: Dict[str, Any]) -> List[str]:
    """Return list of top-level keys whose value changed (or added/removed)."""
    all_keys = set(current) | set(previous)
    changed: List[str] = []
    for k in sorted(all_keys):
        c_val = current.get(k)
        p_val = previous.get(k)
        c_json = _canonical_json(c_val) if c_val is not None else ""
        p_json = _canonical_json(p_val) if p_val is not None else ""
        if c_json != p_json:
            changed.append(k)
    return changed


def check_freeze(run_mode: RunMode) -> FreezeResult:
    """On startup: compare current config hash with last run. If run_mode != DRY_RUN and hash changed, block.

    Returns FreezeResult with allowed, message, changed_keys, config_frozen.
    - DRY_RUN: always allowed, config_frozen=False.
    - PAPER_LIVE/LIVE: if no previous run, allowed and config_frozen=True; if hash matches, allowed and config_frozen=True; if hash differs, blocked and config_frozen=False with changed_keys.
    """
    if run_mode == RunMode.DRY_RUN:
        return FreezeResult(
            allowed=True,
            message="DRY_RUN: config freeze not enforced.",
            changed_keys=[],
            config_frozen=False,
        )

    snapshot = build_critical_config_snapshot()
    current_hash = hash_snapshot(snapshot)
    state = get_config_freeze_state()

    if state is None:
        return FreezeResult(
            allowed=True,
            message="First run with freeze: config frozen for subsequent runs.",
            changed_keys=[],
            config_frozen=True,
        )

    last_hash = state.get("config_hash") or ""
    if current_hash == last_hash:
        return FreezeResult(
            allowed=True,
            message="Config unchanged; execution allowed.",
            changed_keys=[],
            config_frozen=True,
        )

    # Hash changed: compute changed keys for observability
    try:
        previous = json.loads(state.get("config_snapshot") or "{}")
    except (json.JSONDecodeError, TypeError):
        previous = {}
    changed_keys = _changed_keys(snapshot, previous)

    return FreezeResult(
        allowed=False,
        message=(
            "Config changed since last run. Execution blocked. "
            "Revert config or run with RUN_MODE=DRY_RUN to allow. "
            f"Changed keys: {', '.join(changed_keys)}."
        ),
        changed_keys=changed_keys,
        config_frozen=False,
    )


def record_run(snapshot: Dict[str, Any], run_mode: RunMode) -> None:
    """After a successful run, persist config hash and snapshot for next freeze check."""
    current_hash = hash_snapshot(snapshot)
    config_snapshot_str = _canonical_json(snapshot)
    run_mode_str = run_mode.value if hasattr(run_mode, "value") else str(run_mode)
    save_config_freeze_state(current_hash, config_snapshot_str, run_mode_str)
    logger.debug("FreezeGuard: recorded run config_hash=%s run_mode=%s", current_hash[:16], run_mode_str)


__all__ = [
    "FreezeResult",
    "build_critical_config_snapshot",
    "hash_snapshot",
    "check_freeze",
    "record_run",
]
