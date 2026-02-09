# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 5: Data sufficiency — auto-derived from symbol data coverage; manual overrides logged distinctly."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VALID_DATA_SUFFICIENCY = frozenset({"PASS", "WARN", "FAIL"})


def _completeness_to_sufficiency(completeness: float) -> str:
    """Map data_completeness (0-1) to PASS | WARN | FAIL."""
    if completeness >= 0.9:
        return "PASS"
    if completeness >= 0.75:
        return "WARN"
    return "FAIL"


def derive_data_sufficiency(symbol: str) -> Tuple[str, List[str]]:
    """
    Auto-derive data_sufficiency from symbol data coverage (latest evaluation).

    Returns:
        (status, missing_fields) — status in PASS | WARN | FAIL
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return "FAIL", ["symbol_required"]

    try:
        from app.core.eval.evaluation_store import load_latest_run
        run = load_latest_run()
        if run is None or not run.symbols:
            return "FAIL", ["no_evaluation_data"]

        for s in run.symbols:
            s_sym = (getattr(s, "symbol", None) or (s.get("symbol") if isinstance(s, dict) else None) or "").strip().upper()
            if s_sym == sym:
                if isinstance(s, dict):
                    completeness = float(s.get("data_completeness", 0.0) or 0.0)
                    missing = list(s.get("missing_fields") or [])
                else:
                    completeness = float(getattr(s, "data_completeness", 0.0) or 0.0)
                    missing = list(getattr(s, "missing_fields", None) or [])
                return _completeness_to_sufficiency(completeness), missing

        return "FAIL", ["symbol_not_in_latest_evaluation"]
    except Exception as e:
        logger.warning("[DATA_SUFFICIENCY] Failed to derive for %s: %s", sym, e)
        return "FAIL", ["derivation_error"]


def log_data_sufficiency_override(
    position_id: str,
    symbol: str,
    override: str,
    source: str = "MANUAL",
) -> None:
    """Log manual override distinctly (Phase 5)."""
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
    logger.info("[DATA_SUFFICIENCY] Override logged: %s %s -> %s", position_id, symbol, override)


def get_data_sufficiency_for_position(
    symbol: str,
    override: Optional[str] = None,
    override_source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return effective data_sufficiency for a position.

    - If override set (MANUAL): use override, log distinctly (override_source).
    - Else: auto-derive from symbol coverage.
    - Returns: status (PASS|WARN|FAIL), missing_fields, is_override (bool)
    """
    if override and str(override).strip() in VALID_DATA_SUFFICIENCY:
        return {
            "status": str(override).strip(),
            "missing_fields": [],
            "is_override": True,
            "override_source": override_source or "MANUAL",
        }
    status, missing = derive_data_sufficiency(symbol)
    return {
        "status": status,
        "missing_fields": missing,
        "is_override": False,
        "override_source": None,
    }
