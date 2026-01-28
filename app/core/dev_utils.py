# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Dev-only utilities: reset local trading state without touching portfolio/account.

Use for local development and testing. Does not modify trades, positions, or portfolio.
"""

from __future__ import annotations

import logging
import sqlite3

from app.db.database import get_db_path

logger = logging.getLogger(__name__)


def reset_local_trading_state() -> None:
    """Reset local trading state by clearing snapshots and CSP evaluations only.

    Deletes:
    - market_snapshot_data rows
    - market_snapshots rows
    - csp_evaluations rows

    Leaves untouched:
    - symbol_universe, market_regimes, alerts
    - trades, positions, portfolio/account tables
    """
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM csp_evaluations")
        cursor.execute("DELETE FROM market_snapshot_data")
        cursor.execute("DELETE FROM market_snapshots")
        conn.commit()
        logger.info("[DEV] reset_local_trading_state: cleared snapshots and csp_evaluations")
    finally:
        conn.close()

    try:
        from app.core.persistence import create_alert
        create_alert("Local trading state reset (DEV)", level="INFO")
    except Exception:
        pass
