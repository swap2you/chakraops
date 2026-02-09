# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 5: Audit logging — exit events, manual execution intent, data sufficiency overrides."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


def _audit_path() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "audit" / "phase5_actions.jsonl"


def _write_audit(action_type: str, payload: Dict[str, Any]) -> None:
    """Append structured audit record. Includes timestamp, symbol, position_id (if applicable), action_type."""
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action_type": action_type,
        **payload,
    }
    with _LOCK:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.warning("[AUDIT] Failed to write: %s", e)


def audit_exit_event_created(
    position_id: str,
    symbol: str,
    event_type: str,
    exit_reason: str,
) -> None:
    """Log exit event creation (SCALE_OUT or FINAL_EXIT)."""
    _write_audit("exit_event_created", {
        "position_id": position_id,
        "symbol": symbol,
        "event_type": event_type,
        "exit_reason": exit_reason,
    })


def audit_manual_execution_intent(
    position_id: str,
    symbol: str,
    strategy: str,
    account_id: str,
    contracts: Optional[int] = None,
) -> None:
    """Log manual execution intent (position creation)."""
    payload: Dict[str, Any] = {
        "position_id": position_id,
        "symbol": symbol,
        "strategy": strategy,
        "account_id": account_id,
    }
    if contracts is not None:
        payload["contracts"] = contracts
    _write_audit("manual_execution_intent", payload)


def audit_data_sufficiency_override(
    position_id: str,
    symbol: str,
    override: str,
    source: str = "MANUAL",
) -> None:
    """Log data sufficiency manual override."""
    _write_audit("data_sufficiency_override", {
        "position_id": position_id,
        "symbol": symbol,
        "override": override,
        "source": source,
    })
