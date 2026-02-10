# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 5/6: Data sufficiency — structural enforcement from data_dependencies.md."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.symbols.data_dependencies import (
    compute_dependency_lists,
    dependency_status,
    all_missing_fields,
)

logger = logging.getLogger(__name__)

VALID_DATA_SUFFICIENCY = frozenset({"PASS", "WARN", "FAIL"})


def _symbol_to_dict(s: Any) -> Dict[str, Any]:
    """Normalize symbol to dict for dependency computation."""
    if isinstance(s, dict):
        return s
    out = {}
    for k in ("symbol", "price", "bid", "ask", "volume", "avg_option_volume_20d", "avg_stock_volume_20d", "fetched_at", "verdict",
              "data_completeness", "missing_fields", "candidate_trades", "selected_contract"):
        out[k] = getattr(s, k, None)
    out["iv_rank"] = getattr(s, "iv_rank", None)
    out["quote_date"] = getattr(s, "quote_date", None)
    return out


def derive_data_sufficiency(symbol: str) -> Tuple[str, List[str]]:
    """
    Auto-derive data_sufficiency from symbol data coverage (Phase 6: dependency-based).

    Returns:
        (status, missing_fields) — status in PASS | WARN | FAIL.
    """
    result = derive_data_sufficiency_with_dependencies(symbol)
    return result["status"], result["missing_fields"]


def derive_data_sufficiency_with_dependencies(symbol: str) -> Dict[str, Any]:
    """
    Phase 6: Derive data_sufficiency from required/optional/stale lists.
    PASS only when required_data_missing empty AND required_data_stale empty.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return {
            "status": "FAIL",
            "missing_fields": ["symbol_required"],
            "required_data_missing": ["symbol_required"],
            "optional_data_missing": [],
            "required_data_stale": [],
            "data_as_of_orats": None,
            "data_as_of_price": None,
        }

    try:
        from app.core.eval.evaluation_store import load_latest_run
        run = load_latest_run()
        if run is None or not run.symbols:
            return {
                "status": "FAIL",
                "missing_fields": ["no_evaluation_data"],
                "required_data_missing": ["no_evaluation_data"],
                "optional_data_missing": [],
                "required_data_stale": [],
                "data_as_of_orats": None,
                "data_as_of_price": None,
            }

        for s in run.symbols:
            s_sym = (getattr(s, "symbol", None) or (s.get("symbol") if isinstance(s, dict) else None) or "").strip().upper()
            if s_sym != sym:
                continue
            sym_dict = _symbol_to_dict(s)
            required_missing, optional_missing, required_stale, data_as_of = compute_dependency_lists(sym_dict)
            status = dependency_status(required_missing, required_stale, optional_missing)
            missing = all_missing_fields(required_missing, optional_missing)
            return {
                "status": status,
                "missing_fields": missing,
                "required_data_missing": required_missing,
                "optional_data_missing": optional_missing,
                "required_data_stale": required_stale,
                "data_as_of_orats": data_as_of.get("data_as_of_orats"),
                "data_as_of_price": data_as_of.get("data_as_of_price"),
            }

        return {
            "status": "FAIL",
            "missing_fields": ["symbol_not_in_latest_evaluation"],
            "required_data_missing": ["symbol_not_in_latest_evaluation"],
            "optional_data_missing": [],
            "required_data_stale": [],
            "data_as_of_orats": None,
            "data_as_of_price": None,
        }
    except Exception as e:
        logger.warning("[DATA_SUFFICIENCY] Failed to derive for %s: %s", sym, e)
        return {
            "status": "FAIL",
            "missing_fields": ["derivation_error"],
            "required_data_missing": ["derivation_error"],
            "optional_data_missing": [],
            "required_data_stale": [],
            "data_as_of_orats": None,
            "data_as_of_price": None,
        }


def log_data_sufficiency_override(
    position_id: str,
    symbol: str,
    override: str,
    source: str = "MANUAL",
) -> None:
    """Log manual override distinctly (Phase 5). Writes to both overrides.jsonl and audit."""
    import json
    from pathlib import Path
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    log_path = base / "data_sufficiency_overrides.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "position_id": position_id,
        "symbol": symbol,
        "override": override,
        "source": source,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    try:
        from app.core.audit import audit_data_sufficiency_override
        audit_data_sufficiency_override(position_id, symbol, override, source)
    except Exception as e:
        logger.warning("[DATA_SUFFICIENCY] Audit log failed: %s", e)
    logger.info("[DATA_SUFFICIENCY] Override logged: %s %s -> %s", position_id, symbol, override)


def get_data_sufficiency_for_position(
    symbol: str,
    override: Optional[str] = None,
    override_source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return effective data_sufficiency for a position.
    Phase 6: Manual override MUST NOT override when required_data_missing is non-empty.
    """
    derived = derive_data_sufficiency_with_dependencies(symbol)
    required_missing = derived.get("required_data_missing") or []

    if required_missing:
        return {
            "status": "FAIL",
            "missing_fields": derived["missing_fields"],
            "required_data_missing": required_missing,
            "optional_data_missing": derived.get("optional_data_missing") or [],
            "required_data_stale": derived.get("required_data_stale") or [],
            "data_as_of_orats": derived.get("data_as_of_orats"),
            "data_as_of_price": derived.get("data_as_of_price"),
            "is_override": False,
            "override_source": None,
        }

    if override and str(override).strip() in VALID_DATA_SUFFICIENCY:
        return {
            "status": str(override).strip(),
            "missing_fields": [],
            "required_data_missing": [],
            "optional_data_missing": [],
            "required_data_stale": [],
            "data_as_of_orats": derived.get("data_as_of_orats"),
            "data_as_of_price": derived.get("data_as_of_price"),
            "is_override": True,
            "override_source": override_source or "MANUAL",
        }

    return {
        "status": derived["status"],
        "missing_fields": derived["missing_fields"],
        "required_data_missing": derived.get("required_data_missing") or [],
        "optional_data_missing": derived.get("optional_data_missing") or [],
        "required_data_stale": derived.get("required_data_stale") or [],
        "data_as_of_orats": derived.get("data_as_of_orats"),
        "data_as_of_price": derived.get("data_as_of_price"),
        "is_override": False,
        "override_source": None,
    }
