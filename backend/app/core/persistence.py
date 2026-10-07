# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Persistence module for ChakraOps Phase 1A MVP.

This module provides:
- Trade recording (immutable ledger)
- Position management from trades
- Alert lifecycle management (OPEN/ACKED/ARCHIVED)
- Portfolio snapshot management
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.models.position import Position
from app.core.storage.position_store import PositionStore
from app.core.capital_ledger import MonthlySummary
from app.core.position_lifecycle import (
    InvalidLifecycleTransitionError,
    validate_lifecycle_transition,
)
from app.db.database import get_db_path
from app.core.config.paths import DB_PATH

import logging
logger = logging.getLogger(__name__)


def _load_baseline_universe() -> list[str]:
    """Load baseline universe from document.txt (Phase 1B.2).
    
    Returns
    -------
    list[str]
        List of symbols, or empty list if file not found.
    """
    from pathlib import Path
    
    # Look for document.txt in project root
    repo_root = Path(__file__).parent.parent.parent
    doc_file = repo_root / "document.txt"
    
    if not doc_file.exists():
        # Also check in app/data/
        doc_file = repo_root / "app" / "data" / "document.txt"
    
    if not doc_file.exists():
        return []
    
    symbols = []
    try:
        with open(doc_file, "r", encoding="utf-8") as f:
            for line in f:
                symbol = line.strip()
                # Skip empty lines and comments
                if symbol and not symbol.startswith("#"):
                    # Handle various formats: "AAPL", "AAPL - Apple Inc.", etc.
                    symbol = symbol.split()[0].upper() if symbol.split() else symbol.upper()
                    if symbol:
                        symbols.append(symbol)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to load baseline universe from document.txt: {e}")
        return []
    
    return symbols


# Trade action types
TradeAction = str  # "SELL_TO_OPEN", "BUY_TO_CLOSE", "ASSIGN", etc.


def _ensure_candidate_daily_tracking_schema(cursor: sqlite3.Cursor) -> None:
    """Ensure candidate_daily_tracking table has correct schema (idempotent migration).
    
    Creates table if missing, adds updated_at column if missing, backfills data.
    
    Parameters
    ----------
    cursor:
        SQLite cursor for database operations.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Create table if it doesn't exist (with both columns)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidate_daily_tracking (
            date TEXT PRIMARY KEY,
            candidate_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    
    # Check if updated_at column exists
    cursor.execute("PRAGMA table_info(candidate_daily_tracking)")
    columns = [row[1] for row in cursor.fetchall()]
    
    has_updated_at = "updated_at" in columns
    has_created_at = "created_at" in columns
    
    if not has_updated_at:
        # Add updated_at column
        try:
            cursor.execute("ALTER TABLE candidate_daily_tracking ADD COLUMN updated_at TEXT")
            logger.info("[MIGRATION] Added updated_at column to candidate_daily_tracking")
            
            # Backfill updated_at = created_at where NULL
            if has_created_at:
                cursor.execute("""
                    UPDATE candidate_daily_tracking 
                    SET updated_at = created_at 
                    WHERE updated_at IS NULL
                """)
                logger.info("[MIGRATION] Backfilled updated_at from created_at")
        except sqlite3.OperationalError as e:
            # Column might have been added by another process, or table doesn't exist
            logger.debug(f"[MIGRATION] Could not add updated_at (may already exist): {e}")
    else:
        logger.debug("[MIGRATION] candidate_daily_tracking schema already correct (updated_at exists)")
    
    # Ensure created_at exists (should always exist, but defensive)
    if not has_created_at:
        try:
            cursor.execute("ALTER TABLE candidate_daily_tracking ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
            logger.info("[MIGRATION] Added created_at column to candidate_daily_tracking")
        except sqlite3.OperationalError as e:
            logger.debug(f"[MIGRATION] Could not add created_at: {e}")


def init_persistence_db() -> None:
    """Initialize database schema for Phase 1A persistence.
    
    Creates tables:
    - trades: Immutable trade ledger
    - portfolio_snapshots: Manual account value snapshots
    - Updates alerts table with status column
    - Initializes all required tables
    """
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Create trades table (immutable ledger)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                strike REAL,
                expiry TEXT,
                contracts INTEGER NOT NULL,
                premium REAL NOT NULL,
                timestamp TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # Create portfolio_snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_value REAL NOT NULL,
                cash REAL NOT NULL,
                brokerage TEXT DEFAULT 'Robinhood',
                timestamp TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # Add brokerage column if it doesn't exist (migration)
        try:
            cursor.execute("ALTER TABLE portfolio_snapshots ADD COLUMN brokerage TEXT DEFAULT 'Robinhood'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Backfill existing rows with 'Robinhood'
        cursor.execute("""
            UPDATE portfolio_snapshots SET brokerage = 'Robinhood' WHERE brokerage IS NULL
        """)
        
        # Create symbol_universe table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbol_universe (
                symbol TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # Initialize default universe if empty
        cursor.execute("SELECT COUNT(*) FROM symbol_universe")
        count = cursor.fetchone()[0]
        if count == 0:
            default_symbols = [
                ("AAPL", "Apple Inc."),
                ("MSFT", "Microsoft Corporation"),
                ("GOOGL", "Alphabet Inc."),
                ("AMZN", "Amazon.com Inc."),
                ("META", "Meta Platforms Inc."),
                ("SPY", "SPDR S&P 500 ETF"),
                ("QQQ", "Invesco QQQ Trust"),
            ]
            created_at = datetime.now(timezone.utc).isoformat()
            for symbol, note in default_symbols:
                cursor.execute("""
                    INSERT INTO symbol_universe (symbol, enabled, notes, created_at)
                    VALUES (?, 1, ?, ?)
                """, (symbol, note, created_at))
        
        # Ensure alerts table exists before applying migrations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                level TEXT NOT NULL,
                status TEXT DEFAULT 'OPEN',
                created_at TEXT NOT NULL
            )
        """)
        
        # Update alerts table: add status column if it doesn't exist (legacy migration)
        try:
            cursor.execute("ALTER TABLE alerts ADD COLUMN status TEXT DEFAULT 'OPEN'")
        except sqlite3.OperationalError:
            # Column already exists or legacy schema without alerts table; safe to ignore
            pass
        
        # Migrate existing alerts to OPEN status
        cursor.execute("""
            UPDATE alerts SET status = 'OPEN' WHERE status IS NULL
        """)
        
        # Legacy csp_candidates table removed - using csp_evaluations instead (Phase 2B)
        
        # Create assignment_profile table (Phase 1B)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assignment_profile (
                symbol TEXT PRIMARY KEY,
                assignment_score INTEGER NOT NULL,
                assignment_label TEXT NOT NULL,
                operator_override INTEGER DEFAULT 0,
                override_reason TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_action ON trades(action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
        # Legacy csp_candidates index removed - using csp_evaluations instead
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_timestamp ON portfolio_snapshots(timestamp DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_brokerage ON portfolio_snapshots(brokerage)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_universe_enabled ON symbol_universe(enabled)")
        
        # Create assignment_profile table (Phase 1B) - must be before indexes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assignment_profile (
                symbol TEXT PRIMARY KEY,
                assignment_score INTEGER NOT NULL,
                assignment_label TEXT NOT NULL,
                operator_override INTEGER DEFAULT 0,
                override_reason TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Create symbol_cache table (Phase 1B.2) - for ThetaData symbol search
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbol_cache (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                exchange TEXT,
                cached_at TEXT NOT NULL
            )
        """)
        
        # Create indexes for assignment_profile and symbol_cache (after table creation)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignment_label ON assignment_profile(assignment_label)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignment_override ON assignment_profile(operator_override)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbol_cache_symbol ON symbol_cache(symbol)")
        
        # Ensure candidate_daily_tracking schema is correct (migration)
        _ensure_candidate_daily_tracking_schema(cursor)
        
        # Create market_regimes table (Phase 2B)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_regimes (
                snapshot_id TEXT PRIMARY KEY,
                regime TEXT NOT NULL,
                benchmark_symbol TEXT,
                benchmark_return REAL,
                computed_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # Create index for regime lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_regimes_computed_at ON market_regimes(computed_at DESC)")
        
        # Create csp_evaluations table (Phase 2B Step 2)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS csp_evaluations (
                snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                eligible INTEGER NOT NULL,
                score INTEGER NOT NULL,
                reasons_json TEXT,
                features_json TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (snapshot_id, symbol)
            )
        """)
        
        # Create indexes for csp_evaluations
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_csp_eval_snapshot ON csp_evaluations(snapshot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_csp_eval_eligible ON csp_evaluations(eligible, score DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_csp_eval_symbol ON csp_evaluations(symbol)")
        
        # Phase 4.3: trade_proposals table for execution readiness and human acknowledgment
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                proposal_json TEXT NOT NULL,
                execution_status TEXT NOT NULL,
                user_acknowledged INTEGER NOT NULL DEFAULT 0,
                execution_notes TEXT DEFAULT '',
                skipped INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_proposals_decision_ts ON trade_proposals(decision_ts DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_proposals_symbol ON trade_proposals(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_proposals_ack ON trade_proposals(user_acknowledged, skipped)")
        
        # Phase 5.2: rejection analytics daily summary
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rejection_daily_summary (
                date TEXT PRIMARY KEY,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejection_daily_date ON rejection_daily_summary(date DESC)")
        
        # Phase 5.3: trust reports (daily and weekly)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trust_reports (
                report_type TEXT NOT NULL,
                date TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (report_type, date)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trust_reports_type_date ON trust_reports(report_type, date DESC)")
        
        # Phase 6.1: config freeze state (single row: last run hash/snapshot for freeze guard)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_freeze_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                config_hash TEXT NOT NULL,
                config_snapshot TEXT NOT NULL,
                run_mode TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Phase 6.2: daily run cycles (one row per cycle_id = YYYY-MM-DD)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_run_cycles (
                cycle_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                phase TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_run_cycles_cycle_id ON daily_run_cycles(cycle_id)")
        
        # Phase 6.3: position_events (audit trail per position)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS position_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_time TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_position_events_position_id ON position_events(position_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_position_events_event_time ON position_events(event_time DESC)")
        
        # Phase 6.4: capital_ledger_entries (capital movement and outcome accounting)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS capital_ledger_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                position_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                cash_delta REAL NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_capital_ledger_date ON capital_ledger_entries(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_capital_ledger_position ON capital_ledger_entries(position_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_capital_ledger_event ON capital_ledger_entries(event_type)")
        
        # Phase 6.5: decision_artifacts_meta (subset for UI read models)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decision_artifacts_meta (
                decision_ts TEXT PRIMARY KEY,
                meta_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_artifacts_ts ON decision_artifacts_meta(decision_ts DESC)")
        
        conn.commit()
    except Exception as e:
        # Log clear error if schema init fails
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to initialize persistence database: {e}")
        raise
    finally:
        conn.close()
    
    # Initialize market snapshot schema (Phase 2A) AFTER closing persistence connection
    # This avoids concurrent writes to the same SQLite file on Windows.
    from app.core.market_snapshot import init_snapshot_schema
    init_snapshot_schema()


def record_trade(
    symbol: str,
    action: str,
    strike: Optional[float],
    expiry: Optional[str],
    contracts: int,
    premium: float,
    timestamp: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Record a trade in the immutable trades ledger.
    
    Parameters
    ----------
    symbol:
        Stock symbol (e.g., "AAPL").
    action:
        Trade action: "SELL_TO_OPEN", "BUY_TO_CLOSE", "ASSIGN", etc.
    strike:
        Option strike price (None for non-option trades).
    expiry:
        Option expiry date in YYYY-MM-DD format (None for non-option trades).
    contracts:
        Number of contracts (positive integer).
    premium:
        Premium amount (positive for credit, negative for debit).
    timestamp:
        ISO datetime string (defaults to now if not provided).
    notes:
        Optional notes about the trade.
    
    Returns
    -------
    str
        Trade ID (UUID).
    """
    init_persistence_db()
    
    trade_id = str(uuid4())
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            INSERT INTO trades (
                id, symbol, action, strike, expiry,
                contracts, premium, timestamp, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id,
            symbol.upper(),
            action,
            strike,
            expiry,
            contracts,
            premium,
            timestamp,
            notes,
            datetime.now(timezone.utc).isoformat(),
        ))
        
        conn.commit()
    finally:
        conn.close()
    
    return trade_id


def upsert_position_from_trade(trade_id: str) -> Optional[Position]:
    """Create or update a position from a trade.
    
    For SELL_TO_OPEN: Creates a new OPEN position.
    For BUY_TO_CLOSE: Closes the matching position.
    For ASSIGN: Updates position to ASSIGNED state.
    
    Parameters
    ----------
    trade_id:
        Trade ID to process.
    
    Returns
    -------
    Optional[Position]
        Created or updated position, or None if trade doesn't exist.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Fetch trade
        cursor.execute("""
            SELECT symbol, action, strike, expiry, contracts, premium, timestamp, notes
            FROM trades
            WHERE id = ?
        """, (trade_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        symbol, action, strike, expiry, contracts, premium, timestamp, notes = row
        
        # Use same database path as persistence module
        position_store = PositionStore(db_path=get_db_path())
        
        if action == "SELL_TO_OPEN":
            # Create new CSP position
            position = Position.create_csp(
                symbol=symbol,
                strike=strike,
                expiry=expiry,
                contracts=contracts,
                premium_collected=premium,
                notes=notes,
            )
            position.entry_date = timestamp
            position_store.insert_position(position)
            # Phase 6.4: ledger OPEN = credit inflow
            entry_date = timestamp[:10] if timestamp else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            add_capital_ledger_entry(entry_date, position.id, "OPEN", float(premium), notes)
            return position
        
        elif action == "BUY_TO_CLOSE":
            # Find matching open position and close it
            open_positions = position_store.fetch_all_open_positions()
            matching = [
                p for p in open_positions
                if p.symbol == symbol
                and p.strike == strike
                and p.expiry == expiry
            ]
            
            if matching:
                # Close the first matching position
                position = matching[0]
                position.status = "CLOSED"
                position.state = "CLOSED"
                position.lifecycle_state = "CLOSED"
                entry_credit = getattr(position, "entry_credit", None) or position.premium_collected
                # premium from BUY_TO_CLOSE trade is negative (debit)
                realized_pnl = float(entry_credit) + float(premium)
                position.realized_pnl = realized_pnl
                position.close_date = timestamp[:10] if timestamp else datetime.now(timezone.utc).strftime("%Y-%m-%d")
                # Update in database
                cursor.execute("""
                    UPDATE positions
                    SET status = 'CLOSED', state = 'CLOSED', lifecycle_state = 'CLOSED',
                        close_date = ?, realized_pnl = ?
                    WHERE id = ?
                """, (position.close_date, realized_pnl, position.id,))
                conn.commit()
                # Phase 6.4: ledger CLOSE = final reconciliation (realized pnl)
                entry_date = position.close_date
                add_capital_ledger_entry(entry_date, position.id, "CLOSE", realized_pnl, notes)
                return position
        
        elif action == "ASSIGN":
            # Find matching open position and assign it
            open_positions = position_store.fetch_all_open_positions()
            matching = [
                p for p in open_positions
                if p.symbol == symbol
                and p.strike == strike
                and p.expiry == expiry
            ]
            
            if matching:
                position = matching[0]
                position.status = "ASSIGNED"
                position.state = "ASSIGNED"
                position.lifecycle_state = "ASSIGNED"
                # Update in database
                cursor.execute("""
                    UPDATE positions
                    SET status = 'ASSIGNED', state = 'ASSIGNED', lifecycle_state = 'ASSIGNED'
                    WHERE id = ?
                """, (position.id,))
                conn.commit()
                # Phase 6.4: ledger ASSIGNMENT = capital adjustment (0 if no cash delta)
                entry_date = timestamp[:10] if timestamp else datetime.now(timezone.utc).strftime("%Y-%m-%d")
                add_capital_ledger_entry(entry_date, position.id, "ASSIGNMENT", 0.0, notes)
                return position
        
        return None
    finally:
        conn.close()


def recompute_positions() -> List[Position]:
    """Recompute all positions from trades ledger.
    
    This processes all trades in chronological order and rebuilds
    the positions table. Useful for data recovery or migration.
    
    Returns
    -------
    List[Position]
        List of all computed positions.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Fetch all trades in chronological order
        cursor.execute("""
            SELECT id, symbol, action, strike, expiry, contracts, premium, timestamp, notes
            FROM trades
            ORDER BY timestamp ASC
        """)
        
        trades = cursor.fetchall()
        
        # Clear existing positions
        cursor.execute("DELETE FROM positions")
        conn.commit()
        
        # Process trades and rebuild positions
        position_store = PositionStore(db_path=get_db_path())
        positions = []
        
        for trade in trades:
            trade_id, symbol, action, strike, expiry, contracts, premium, timestamp, notes = trade
            position = upsert_position_from_trade(trade_id)
            if position:
                positions.append(position)
        
        return positions
    finally:
        conn.close()


def list_open_positions() -> List[Position]:
    """List all open positions from database.
    
    Returns
    -------
    List[Position]
        List of open positions.
    """
    position_store = PositionStore(db_path=get_db_path())
    return position_store.fetch_all_open_positions()


def mark_candidate_executed(symbol: str, executed: bool = True) -> None:
    """Legacy function - DEPRECATED.
    
    CSP candidates are now stored in csp_evaluations table.
    Execution tracking should be done via trades table using record_trade().
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"[DEPRECATED] mark_candidate_executed() is deprecated. Use record_trade() instead.")
    # No-op: csp_candidates table no longer exists


def list_candidates(include_executed: bool = False) -> List[Dict[str, Any]]:
    """Legacy function - DEPRECATED.
    
    Returns empty list. CSP candidates are now stored in csp_evaluations table.
    Use get_csp_evaluations(snapshot_id) instead.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("[DEPRECATED] list_candidates() is deprecated. Use get_csp_evaluations() instead.")
    return []


def create_alert(message: str, level: str = "INFO") -> int:
    """Create a new alert with OPEN status.
    
    Only operator-facing alerts should be created:
    - INFO: Daily plan, system status
    - WATCH: Potential issue, no action yet
    - ACTION: Operator decision required
    - HALT: System blocked
    
    System/internal errors should NOT be persisted as alerts.
    Use logger.error() or logger.warn() instead.
    
    Parameters
    ----------
    message:
        Alert message text.
    level:
        Alert level: "INFO", "WATCH", "ACTION", "HALT".
    
    Returns
    -------
    int
        Alert ID.
    """
    # Validate level
    valid_levels = ["INFO", "WATCH", "ACTION", "HALT"]
    if level not in valid_levels:
        level = "INFO"  # Default to INFO for invalid levels
    
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO alerts (message, level, status, created_at)
            VALUES (?, ?, 'OPEN', ?)
        """, (
            message,
            level,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_alerts(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List alerts, optionally filtered by status.
    
    Parameters
    ----------
    status:
        Filter by status: "OPEN", "ACKED", "ARCHIVED", or None for all.
    
    Returns
    -------
    List[Dict[str, Any]]
        List of alert dictionaries.
    """
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return []
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        if status:
            cursor.execute("""
                SELECT id, message, level, status, created_at
                FROM alerts
                WHERE status = ?
                ORDER BY created_at DESC
            """, (status,))
        else:
            cursor.execute("""
                SELECT id, message, level, status, created_at
                FROM alerts
                ORDER BY created_at DESC
            """)
        
        rows = cursor.fetchall()
        alerts = []
        for row in rows:
            alerts.append({
                "id": row[0],
                "message": row[1],
                "level": row[2],
                "status": row[3] if len(row) > 3 else "OPEN",
                "created_at": row[4],
            })
        return alerts
    finally:
        conn.close()


def ack_alert(alert_id: int) -> None:
    """Acknowledge an alert (change status to ACKED).
    
    Parameters
    ----------
    alert_id:
        Alert ID to acknowledge.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE alerts
            SET status = 'ACKED'
            WHERE id = ?
        """, (alert_id,))
        conn.commit()
    finally:
        conn.close()


def archive_alert(alert_id: int) -> None:
    """Archive an alert (change status to ARCHIVED).
    
    Parameters
    ----------
    alert_id:
        Alert ID to archive.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE alerts
            SET status = 'ARCHIVED'
            WHERE id = ?
        """, (alert_id,))
        conn.commit()
    finally:
        conn.close()


def bulk_ack_alerts(alert_ids: list[int]) -> None:
    """
    Acknowledge multiple alerts by id.
    Thin wrapper over ack_alert().
    """
    for alert_id in alert_ids:
        ack_alert(alert_id)


def bulk_archive_non_action_alerts(alert_ids: list[int]) -> None:
    """
    Archive alerts that are not ACTION level.
    Caller is responsible for filtering ids.
    """
    for alert_id in alert_ids:
        archive_alert(alert_id)


def save_portfolio_snapshot(
    account_value: float,
    cash: float,
    brokerage: str = "Robinhood",
    timestamp: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    """Save a portfolio snapshot.
    
    Parameters
    ----------
    account_value:
        Total account value.
    cash:
        Cash balance.
    brokerage:
        Brokerage name: "Robinhood", "Fidelity", "Charles Schwab" (default: "Robinhood").
    timestamp:
        ISO datetime string (defaults to now if not provided).
    notes:
        Optional notes.
    
    Returns
    -------
    int
        Snapshot ID.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            INSERT INTO portfolio_snapshots (account_value, cash, brokerage, timestamp, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            account_value,
            cash,
            brokerage,
            timestamp,
            notes,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_latest_portfolio_snapshot(brokerage: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get the latest portfolio snapshot.
    
    Parameters
    ----------
    brokerage:
        Filter by brokerage name. If None, returns latest across all brokerages.
    
    Returns
    -------
    Optional[Dict[str, Any]]
        Latest snapshot dictionary, or None if no snapshots exist.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return None
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        if brokerage:
            cursor.execute("""
                SELECT id, account_value, cash, brokerage, timestamp, notes, created_at
                FROM portfolio_snapshots
                WHERE brokerage = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (brokerage,))
        else:
            cursor.execute("""
                SELECT id, account_value, cash, brokerage, timestamp, notes, created_at
                FROM portfolio_snapshots
                ORDER BY timestamp DESC
                LIMIT 1
            """)
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "account_value": row[1],
            "cash": row[2],
            "brokerage": row[3] if len(row) > 3 else "Robinhood",
            "timestamp": row[4],
            "notes": row[5],
            "created_at": row[6],
        }
    finally:
        conn.close()


# Universe management functions

def get_enabled_symbols() -> list[str]:
    """
    Return list of enabled symbols from symbol_universe.
    This is the canonical universe filter used by the system.
    Symbols are normalized (UPPER, TRIM) for consistency.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    from app.core.market_snapshot import normalize_symbol
    from app.db.database import get_db_path
    
    # Diagnostic logging (Heartbeat Diagnostic Verification)
    db_path = get_db_path()
    logger.info(f"[HEARTBEAT][DB] path={db_path.absolute()}")
    
    # Direct query to verify universe state
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='symbol_universe'
        """)
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            logger.warning("[HEARTBEAT][UNIVERSE] Table symbol_universe does not exist")
            return []
        
        # Get total row count
        cursor.execute("SELECT COUNT(*) FROM symbol_universe")
        total_rows = cursor.fetchone()[0]
        logger.info(f"[HEARTBEAT][UNIVERSE] total_rows={total_rows}")
        
        # Get enabled row count
        cursor.execute("SELECT COUNT(*) FROM symbol_universe WHERE enabled=1")
        enabled_rows = cursor.fetchone()[0]
        logger.info(f"[HEARTBEAT][UNIVERSE] enabled_rows={enabled_rows}")
        
        # Get sample rows (first 10)
        cursor.execute("""
            SELECT symbol, enabled, notes 
            FROM symbol_universe 
            ORDER BY symbol 
            LIMIT 10
        """)
        sample_rows = cursor.fetchall()
        logger.info(f"[HEARTBEAT][UNIVERSE] sample={sample_rows}")
        
        # Get all enabled symbols (direct query - no additional filters)
        cursor.execute("""
            SELECT symbol, enabled, notes 
            FROM symbol_universe 
            WHERE enabled=1
            ORDER BY symbol
        """)
        enabled_raw = cursor.fetchall()
        logger.info(f"[HEARTBEAT][UNIVERSE] enabled_raw_count={len(enabled_raw)}")
        if enabled_raw:
            logger.info(f"[HEARTBEAT][UNIVERSE] enabled_raw_sample={enabled_raw[:10]}")
        
    finally:
        conn.close()
    
    # Use existing list_universe_symbols() for consistency
    symbols = list_universe_symbols()
    
    # Filter and normalize
    enabled_list = []
    for row in symbols:
        if row.get("enabled"):
            normalized = normalize_symbol(row["symbol"])
            if normalized:
                enabled_list.append(normalized)
    
    logger.info(f"[HEARTBEAT][UNIVERSE] final_enabled_count={len(enabled_list)}")
    if enabled_list:
        logger.info(f"[HEARTBEAT][UNIVERSE] final_enabled_sample={enabled_list[:10]}")
    
    return enabled_list


def get_all_symbols() -> List[Dict[str, Any]]:
    """Get all symbols from universe (Phase 2B Step 4).
    
    Returns
    -------
    List[Dict[str, Any]]
        List of symbol dictionaries with symbol, enabled, notes.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT symbol, enabled, notes
            FROM symbol_universe
            ORDER BY symbol
        """)
        rows = cursor.fetchall()
        return [
            {
                "symbol": row[0],
                "enabled": bool(row[1]),
                "notes": row[2] or "",
            }
            for row in rows
        ]
    finally:
        conn.close()


def list_universe_symbols() -> List[Dict[str, Any]]:
    """List all symbols in universe.
    
    Returns
    -------
    List[Dict[str, Any]]
        List of symbol dictionaries with symbol, enabled, notes, created_at.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Defensive check: ensure symbol_universe table exists (Universe Manager must work independently)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbol_universe (
                symbol TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            SELECT symbol, enabled, notes, created_at
            FROM symbol_universe
            ORDER BY symbol
        """)
        rows = cursor.fetchall()
        return [
            {
                "symbol": row[0],
                "enabled": bool(row[1]),
                "notes": row[2],
                "created_at": row[3],
            }
            for row in rows
        ]
    finally:
        conn.close()


def add_symbol(symbol: str, notes: str = "") -> None:
    """Add a symbol to the universe (Phase 2B Step 4).
    
    Parameters
    ----------
    symbol:
        Stock symbol (e.g., "AAPL").
    notes:
        Optional notes about the symbol.
    """
    from app.core.market_snapshot import normalize_symbol
    
    normalized = normalize_symbol(symbol)
    if not normalized:
        logger.warning(f"[UNIVERSE] Invalid symbol: {symbol}")
        return
    
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if already exists
        cursor.execute("SELECT COUNT(*) FROM symbol_universe WHERE symbol = ?", (normalized,))
        exists = cursor.fetchone()[0] > 0
        
        if exists:
            logger.warning(f"[UNIVERSE] Symbol {normalized} already exists, ignoring add")
            return
        
        created_at = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO symbol_universe (symbol, enabled, notes, created_at)
            VALUES (?, 1, ?, ?)
        """, (normalized, notes, created_at))
        conn.commit()
        logger.info(f"[UNIVERSE] Added symbol: {normalized}")
    finally:
        conn.close()


def add_universe_symbol(symbol: str, enabled: bool = True, notes: Optional[str] = None) -> None:
    """Add or update a symbol in the universe (legacy function).
    
    Parameters
    ----------
    symbol:
        Stock symbol (e.g., "AAPL").
    enabled:
        Whether symbol is enabled for CSP candidate generation.
    notes:
        Optional notes about the symbol.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO symbol_universe (symbol, enabled, notes, created_at)
            VALUES (?, ?, ?, ?)
        """, (symbol.upper(), 1 if enabled else 0, notes, created_at))
        conn.commit()
    finally:
        conn.close()


def toggle_symbol(symbol: str, enabled: bool) -> None:
    """Toggle enabled status of a symbol (Phase 2B Step 4).
    
    Parameters
    ----------
    symbol:
        Stock symbol to toggle.
    enabled:
        New enabled status.
    """
    from app.core.market_snapshot import normalize_symbol
    
    normalized = normalize_symbol(symbol)
    if not normalized:
        logger.warning(f"[UNIVERSE] Invalid symbol: {symbol}")
        return
    
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE symbol_universe SET enabled = ? WHERE symbol = ?
        """, (1 if enabled else 0, normalized))
        conn.commit()
        logger.info(f"[UNIVERSE] Toggled {normalized} to enabled={enabled}")
    finally:
        conn.close()


def toggle_universe_symbol(symbol: str, enabled: bool) -> None:
    """Toggle enabled status of a symbol (legacy function).
    
    Parameters
    ----------
    symbol:
        Stock symbol to toggle.
    enabled:
        New enabled status.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE symbol_universe SET enabled = ? WHERE symbol = ?
        """, (1 if enabled else 0, symbol.upper()))
        conn.commit()
    finally:
        conn.close()


def update_symbol(symbol: str, enabled: bool, notes: str) -> None:
    """Update a symbol's enabled status and notes (Phase 2B Step 4).
    
    Parameters
    ----------
    symbol:
        Stock symbol to update.
    enabled:
        New enabled status.
    notes:
        New notes.
    """
    from app.core.market_snapshot import normalize_symbol
    
    normalized = normalize_symbol(symbol)
    if not normalized:
        logger.warning(f"[UNIVERSE] Invalid symbol: {symbol}")
        return
    
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE symbol_universe SET enabled = ?, notes = ? WHERE symbol = ?
        """, (1 if enabled else 0, notes, normalized))
        conn.commit()
        logger.info(f"[UNIVERSE] Updated {normalized}: enabled={enabled}")
    finally:
        conn.close()


def delete_symbol(symbol: str) -> None:
    """Delete a symbol from the universe (Phase 2B Step 4).
    
    Parameters
    ----------
    symbol:
        Stock symbol to delete.
    """
    from app.core.market_snapshot import normalize_symbol
    
    normalized = normalize_symbol(symbol)
    if not normalized:
        logger.warning(f"[UNIVERSE] Invalid symbol: {symbol}")
        return
    
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM symbol_universe WHERE symbol = ?
        """, (normalized,))
        conn.commit()
        logger.info(f"[UNIVERSE] Deleted symbol: {normalized}")
    finally:
        conn.close()


def delete_universe_symbol(symbol: str) -> None:
    """Delete a symbol from the universe (legacy function).
    
    Parameters
    ----------
    symbol:
        Stock symbol to delete.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM symbol_universe WHERE symbol = ?
        """, (symbol.upper(),))
        conn.commit()
    finally:
        conn.close()


def reset_local_trading_state() -> None:
    """Reset local trading state by deleting and reinitializing database.
    
    WARNING: This deletes all local trading data including:
    - Trades
    - Positions
    - Alerts
    - Portfolio snapshots
    - CSP candidates
    
    This does NOT affect:
    - Code
    - Schema definitions
    - Tests
    - Config files
    """
    import logging
    logger = logging.getLogger(__name__)
    
    db_path = get_db_path()
    
    # Delete database file
    if db_path.exists():
        db_path.unlink()
        logger.info(f"Deleted database file: {db_path}")
    
    # Reinitialize schema
    from app.db.database import init_db
    init_db()
    logger.info("Reinitialized database schema")
    
    # Log reset event
    create_alert("Local trading state reset (DEV)", level="INFO")


# Assignment profile management functions (Phase 1B)

def save_assignment_profile(
    symbol: str,
    assignment_score: int,
    assignment_label: str,
    operator_override: bool = False,
    override_reason: Optional[str] = None,
) -> None:
    """Save or update assignment profile for a symbol.
    
    Parameters
    ----------
    symbol:
        Stock symbol.
    assignment_score:
        Assignment score (0-100).
    assignment_label:
        Assignment label: "OK_TO_OWN", "NEUTRAL", or "RENT_ONLY".
    operator_override:
        Whether operator has overridden the assignment blocking.
    override_reason:
        Optional reason for override.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Defensive check: ensure assignment_profile table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assignment_profile (
                symbol TEXT PRIMARY KEY,
                assignment_score INTEGER NOT NULL,
                assignment_label TEXT NOT NULL,
                operator_override INTEGER DEFAULT 0,
                override_reason TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        
        updated_at = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO assignment_profile (
                symbol, assignment_score, assignment_label,
                operator_override, override_reason, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            symbol.upper(),
            assignment_score,
            assignment_label,
            1 if operator_override else 0,
            override_reason,
            updated_at,
        ))
        conn.commit()
    finally:
        conn.close()


def get_assignment_profile(symbol: str) -> Optional[Dict[str, Any]]:
    """Get assignment profile for a symbol.
    
    Parameters
    ----------
    symbol:
        Stock symbol.
    
    Returns
    -------
    Optional[Dict[str, Any]]
        Assignment profile dictionary, or None if not found.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Defensive check: ensure assignment_profile table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assignment_profile (
                symbol TEXT PRIMARY KEY,
                assignment_score INTEGER NOT NULL,
                assignment_label TEXT NOT NULL,
                operator_override INTEGER DEFAULT 0,
                override_reason TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            SELECT symbol, assignment_score, assignment_label,
                   operator_override, override_reason, updated_at
            FROM assignment_profile
            WHERE symbol = ?
        """, (symbol.upper(),))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "symbol": row[0],
            "assignment_score": row[1],
            "assignment_label": row[2],
            "operator_override": bool(row[3]),
            "override_reason": row[4],
            "updated_at": row[5],
        }
    finally:
        conn.close()


def set_assignment_override(
    symbol: str,
    override: bool,
    reason: Optional[str] = None,
) -> None:
    """Set operator override for assignment blocking.
    
    Parameters
    ----------
    symbol:
        Stock symbol.
    override:
        True to enable override, False to disable.
    reason:
        Optional reason for override.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Defensive check: ensure assignment_profile table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assignment_profile (
                symbol TEXT PRIMARY KEY,
                assignment_score INTEGER NOT NULL,
                assignment_label TEXT NOT NULL,
                operator_override INTEGER DEFAULT 0,
                override_reason TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        
        updated_at = datetime.now(timezone.utc).isoformat()
        
        # Check if profile exists
        cursor.execute("SELECT symbol FROM assignment_profile WHERE symbol = ?", (symbol.upper(),))
        exists = cursor.fetchone() is not None
        
        if exists:
            # Update existing profile
            cursor.execute("""
                UPDATE assignment_profile
                SET operator_override = ?, override_reason = ?, updated_at = ?
                WHERE symbol = ?
            """, (1 if override else 0, reason, updated_at, symbol.upper()))
        else:
            # Create new profile with default values (will be updated by scoring)
            cursor.execute("""
                INSERT INTO assignment_profile (
                    symbol, assignment_score, assignment_label,
                    operator_override, override_reason, updated_at
                )
                VALUES (?, 0, 'RENT_ONLY', ?, ?, ?)
            """, (symbol.upper(), 1 if override else 0, reason, updated_at))
        
        conn.commit()
    finally:
        conn.close()


def is_assignment_blocked(symbol: str) -> bool:
    """Check if CSP is blocked for a symbol due to assignment-worthiness.
    
    Returns True if:
    - Assignment label is RENT_ONLY AND
    - Operator override is False
    
    Parameters
    ----------
    symbol:
        Stock symbol.
    
    Returns
    -------
    bool
        True if blocked, False if allowed.
    """
    profile = get_assignment_profile(symbol)
    if not profile:
        return False  # No profile = not blocked (will be scored on first evaluation)
    
    if profile["assignment_label"] == "RENT_ONLY" and not profile["operator_override"]:
        return True
    
    return False


def upsert_regime(
    snapshot_id: str,
    regime: str,
    benchmark_symbol: Optional[str] = None,
    benchmark_return: Optional[float] = None,
    computed_at: Optional[str] = None,
) -> None:
    """Upsert market regime for a snapshot (Phase 2B).
    
    Parameters
    ----------
    snapshot_id:
        Snapshot ID this regime is computed for.
    regime:
        Regime value: "BULL", "BEAR", "NEUTRAL", or "UNKNOWN".
    benchmark_symbol:
        Optional benchmark symbol used (e.g., "SPY", "SPX", "QQQ").
    benchmark_return:
        Optional return value computed (p2 - p1) / p1.
    computed_at:
        Optional ISO timestamp when regime was computed (defaults to now).
    """
    if computed_at is None:
        computed_at = datetime.now(timezone.utc).isoformat()
    
    created_at = datetime.now(timezone.utc).isoformat()
    
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO market_regimes (
                snapshot_id, regime, benchmark_symbol, benchmark_return,
                computed_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (snapshot_id, regime, benchmark_symbol, benchmark_return, computed_at, created_at))
        
        conn.commit()
    finally:
        conn.close()


def get_latest_regime() -> Optional[Dict[str, Any]]:
    """Get the latest market regime from database (Phase 2B).
    
    Returns
    -------
    Optional[Dict[str, Any]]
        Dictionary with:
        - snapshot_id: str
        - regime: str ("BULL", "BEAR", "NEUTRAL", "UNKNOWN")
        - benchmark_symbol: Optional[str]
        - benchmark_return: Optional[float]
        - computed_at: str
        Or None if no regime exists.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return None
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT snapshot_id, regime, benchmark_symbol, benchmark_return, computed_at
            FROM market_regimes
            ORDER BY computed_at DESC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        if row:
            return {
                "snapshot_id": row[0],
                "regime": row[1],
                "benchmark_symbol": row[2],
                "benchmark_return": row[3],
                "computed_at": row[4],
            }
        return None
    finally:
        conn.close()


def upsert_csp_evaluations(snapshot_id: str, rows: List[Dict[str, Any]]) -> None:
    """Upsert CSP evaluation results for a snapshot (Phase 2B Step 2).
    
    Parameters
    ----------
    snapshot_id:
        Snapshot ID these evaluations belong to.
    rows:
        List of evaluation dictionaries, each with:
        - symbol: str
        - eligible: bool
        - score: int (0-100)
        - rejection_reasons: List[str]
        - features: Dict[str, Any]
        - regime_context: Dict[str, Any]
    """
    if not rows:
        return
    
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        
        for row in rows:
            symbol = row["symbol"]
            eligible = 1 if row.get("eligible", False) else 0
            score = row.get("score", 0)
            rejection_reasons = row.get("rejection_reasons", [])
            features = row.get("features", {})
            regime_context = row.get("regime_context", {})
            
            # Combine features and regime_context into features_json
            combined_features = {**features, "regime_context": regime_context}
            
            reasons_json = json.dumps(rejection_reasons)
            features_json = json.dumps(combined_features)
            
            cursor.execute("""
                INSERT OR REPLACE INTO csp_evaluations (
                    snapshot_id, symbol, eligible, score,
                    reasons_json, features_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (snapshot_id, symbol, eligible, score, reasons_json, features_json, created_at))
        
        conn.commit()
    finally:
        conn.close()


def get_csp_evaluations(snapshot_id: str) -> List[Dict[str, Any]]:
    """Get CSP evaluation results for a snapshot (Phase 2B Step 2).
    
    Parameters
    ----------
    snapshot_id:
        Snapshot ID to load evaluations for.
    
    Returns
    -------
    List[Dict[str, Any]]
        List of evaluation dictionaries with:
        - symbol: str
        - eligible: bool
        - score: int
        - rejection_reasons: List[str]
        - features: Dict[str, Any]
        - regime_context: Dict[str, Any]
    """
    db_path = get_db_path()
    if not db_path.exists():
        return []
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT symbol, eligible, score, reasons_json, features_json
            FROM csp_evaluations
            WHERE snapshot_id = ?
            ORDER BY score DESC
        """, (snapshot_id,))
        
        results = []
        for row in cursor.fetchall():
            symbol = row[0]
            eligible = bool(row[1])
            score = row[2]
            reasons_json = row[3]
            features_json = row[4]
            
            rejection_reasons = json.loads(reasons_json) if reasons_json else []
            combined_features = json.loads(features_json) if features_json else {}
            
            # Split features and regime_context
            regime_context = combined_features.pop("regime_context", {})
            features = combined_features
            
            results.append({
                "symbol": symbol,
                "eligible": eligible,
                "score": score,
                "rejection_reasons": rejection_reasons,
                "features": features,
                "regime_context": regime_context,
            })
        
        return results
    finally:
        conn.close()


def get_rejection_reason_counts(snapshot_id: str) -> List[tuple[str, int]]:
    """Get rejection reason counts for a snapshot (Phase 2B Step 2).
    
    Parameters
    ----------
    snapshot_id:
        Snapshot ID to analyze.
    
    Returns
    -------
    List[tuple[str, int]]
        List of (reason, count) tuples, sorted by count descending.
    """
    evaluations = get_csp_evaluations(snapshot_id)
    
    reason_counts: Dict[str, int] = {}
    for eval_result in evaluations:
        if not eval_result["eligible"]:
            for reason in eval_result["rejection_reasons"]:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
    
    # Sort by count descending
    return sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)


def save_trade_proposal(
    decision_ts: str,
    proposal_json: Dict[str, Any],
    execution_status: str = "BLOCKED",
) -> int:
    """Store a trade proposal in DB (Phase 4.3). Returns row id."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        symbol = str(proposal_json.get("symbol", ""))
        strategy_type = str(proposal_json.get("strategy_type", ""))
        cursor.execute("""
            INSERT INTO trade_proposals (
                decision_ts, symbol, strategy_type, proposal_json,
                execution_status, user_acknowledged, execution_notes, skipped,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, '', 0, ?, ?)
        """, (decision_ts, symbol, strategy_type, json.dumps(proposal_json), execution_status, now, now))
        conn.commit()
        return cursor.lastrowid or 0
    finally:
        conn.close()


def get_latest_trade_proposal(symbol: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get the most recent trade proposal from DB (Phase 4.3). If symbol given, filter by symbol."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        if symbol:
            cursor.execute("""
                SELECT proposal_json, execution_status, user_acknowledged, execution_notes, skipped, decision_ts
                FROM trade_proposals WHERE symbol = ? ORDER BY id DESC LIMIT 1
            """, (symbol.upper(),))
        else:
            cursor.execute("""
                SELECT proposal_json, execution_status, user_acknowledged, execution_notes, skipped, decision_ts
                FROM trade_proposals ORDER BY id DESC LIMIT 1
            """)
        row = cursor.fetchone()
        if not row:
            return None
        proposal_data = json.loads(row[0])
        proposal_data["execution_status"] = row[1]
        proposal_data["user_acknowledged"] = bool(row[2])
        proposal_data["execution_notes"] = row[3] or ""
        proposal_data["skipped"] = bool(row[4])
        proposal_data["decision_ts"] = row[5]
        return proposal_data
    finally:
        conn.close()


def update_trade_proposal_acknowledgment(
    proposal_id: int,
    user_acknowledged: bool,
    execution_notes: str = "",
    skipped: bool = False,
) -> None:
    """Update acknowledgment and notes for a trade proposal (Phase 4.3)."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            UPDATE trade_proposals
            SET user_acknowledged = ?, execution_notes = ?, skipped = ?, updated_at = ?
            WHERE id = ?
        """, (1 if user_acknowledged else 0, execution_notes or "", 1 if skipped else 0, now, proposal_id))
        conn.commit()
    finally:
        conn.close()


def save_daily_rejection_summary(date_str: str, summary: Dict[str, Any]) -> None:
    """Store daily rejection summary (Phase 5.2). Overwrites existing row for date_str."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO rejection_daily_summary (date, summary_json, created_at)
            VALUES (?, ?, ?)
        """, (date_str, json.dumps(summary), now))
        conn.commit()
    finally:
        conn.close()


def get_rejection_history(days: int = 30) -> List[Dict[str, Any]]:
    """Get rejection summaries for the last N days (Phase 5.2). Returns list of {date, ...summary}."""
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT date, summary_json FROM rejection_daily_summary
            ORDER BY date DESC LIMIT ?
        """, (max(1, days),))
        rows = cursor.fetchall()
        result = []
        for date_val, summary_json in rows:
            summary = json.loads(summary_json) if summary_json else {}
            summary["date"] = date_val
            result.append(summary)
        return result
    finally:
        conn.close()


def save_trust_report(report_type: str, date_str: str, report: Dict[str, Any]) -> None:
    """Store a trust report (Phase 5.3). report_type: 'daily' or 'weekly'. Overwrites existing row."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO trust_reports (report_type, date, report_json, created_at)
            VALUES (?, ?, ?, ?)
        """, (report_type, date_str, json.dumps(report), now))
        conn.commit()
    finally:
        conn.close()


def get_trust_report_history(report_type: str, days: int = 30) -> List[Dict[str, Any]]:
    """Get trust reports for the last N days (Phase 5.3). Returns list of {date, ...report}."""
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT date, report_json FROM trust_reports
            WHERE report_type = ?
            ORDER BY date DESC LIMIT ?
        """, (report_type, max(1, days)))
        rows = cursor.fetchall()
        result = []
        for date_val, report_json in rows:
            report = json.loads(report_json) if report_json else {}
            report["date"] = date_val
            result.append(report)
        return result
    finally:
        conn.close()


def save_config_freeze_state(config_hash: str, config_snapshot: str, run_mode: str) -> None:
    """Store last run config hash and snapshot (Phase 6.1). Single row id=1."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO config_freeze_state (id, config_hash, config_snapshot, run_mode, updated_at)
            VALUES (1, ?, ?, ?, ?)
        """, (config_hash, config_snapshot, run_mode, now))
        conn.commit()
    finally:
        conn.close()


def get_config_freeze_state() -> Optional[Dict[str, Any]]:
    """Get last run config freeze state (Phase 6.1). Returns dict with config_hash, config_snapshot, run_mode, updated_at or None."""
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT config_hash, config_snapshot, run_mode, updated_at FROM config_freeze_state WHERE id = 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "config_hash": row[0],
            "config_snapshot": row[1],
            "run_mode": row[2],
            "updated_at": row[3],
        }
    finally:
        conn.close()


def get_daily_run_cycle(cycle_id: str) -> Optional[Dict[str, Any]]:
    """Get daily run cycle by cycle_id (Phase 6.2). Returns dict with cycle_id, started_at, completed_at, phase, updated_at or None."""
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT cycle_id, started_at, completed_at, phase, updated_at FROM daily_run_cycles WHERE cycle_id = ?
        """, (cycle_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "cycle_id": row[0],
            "started_at": row[1],
            "completed_at": row[2],
            "phase": row[3],
            "updated_at": row[4],
        }
    finally:
        conn.close()


def start_daily_run_cycle(cycle_id: str, phase: str = "SNAPSHOT") -> None:
    """Start or ensure a daily run cycle exists (Phase 6.2). Inserts with phase SNAPSHOT if new."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT OR IGNORE INTO daily_run_cycles (cycle_id, started_at, completed_at, phase, updated_at)
            VALUES (?, ?, NULL, ?, ?)
        """, (cycle_id, now, phase, now))
        conn.commit()
    finally:
        conn.close()


def update_daily_run_cycle_phase(cycle_id: str, phase: str) -> None:
    """Update daily run cycle phase (Phase 6.2)."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            UPDATE daily_run_cycles SET phase = ?, updated_at = ? WHERE cycle_id = ?
        """, (phase, now, cycle_id))
        conn.commit()
    finally:
        conn.close()


def set_daily_run_cycle_complete(cycle_id: str) -> None:
    """Set daily run cycle to COMPLETE and set completed_at (Phase 6.2)."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            UPDATE daily_run_cycles SET phase = 'COMPLETE', completed_at = ?, updated_at = ? WHERE cycle_id = ?
        """, (now, now, cycle_id))
        conn.commit()
    finally:
        conn.close()


def add_position_event(
    position_id: str,
    event_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a position event (Phase 6.3). event_type: OPENED, TARGET_1_HIT, STOP_TRIGGERED, CLOSED, etc."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        cursor.execute("""
            INSERT INTO position_events (position_id, event_type, event_time, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (position_id, event_type, now, meta_json, now))
        conn.commit()
    finally:
        conn.close()


def get_position_history(position_id: str) -> List[Dict[str, Any]]:
    """Return events for a position, oldest first (Phase 6.3). Reconstructs full trade story."""
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT position_id, event_type, event_time, metadata
            FROM position_events
            WHERE position_id = ?
            ORDER BY event_time ASC
        """, (position_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            pos_id, ev_type, ev_time, meta_str = row
            meta = {}
            if meta_str:
                try:
                    meta = json.loads(meta_str)
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append({
                "position_id": pos_id,
                "event_type": ev_type,
                "event_time": ev_time,
                "metadata": meta,
            })
        return result
    finally:
        conn.close()


def get_position_by_id(position_id: str) -> Optional[Position]:
    """Fetch a single position by id (Phase 6.7). Returns None if not found."""
    init_persistence_db()
    store = PositionStore(db_path=get_db_path())
    return store.fetch_position_by_id(position_id)


def create_manual_position(
    symbol: str,
    strategy_type: str,
    expiry: Optional[str],
    strike: Optional[float],
    contracts: int,
    entry_credit: float,
    open_date: str,
    notes: Optional[str] = None,
) -> Position:
    """Create a position manually (Phase 6.7). Inserts position, OPENED event, and ledger OPEN.
    lifecycle_state starts at OPEN. strategy_type: CSP or SHARES."""
    init_persistence_db()
    db_path = get_db_path()
    store = PositionStore(db_path=db_path)
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    contracts = max(1, int(contracts))
    entry_credit = float(entry_credit) if entry_credit is not None else 0.0
    open_date = (open_date or "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    notes = notes or ""

    if (strategy_type or "").upper() == "SHARES":
        position = Position.create_shares(symbol=symbol, shares=contracts, notes=notes)
        position.entry_credit = entry_credit
        position.open_date = open_date
        position.entry_date = open_date + "T12:00:00+00:00"
    else:
        if strike is None:
            raise ValueError("strike is required for CSP")
        if not expiry:
            raise ValueError("expiry is required for CSP")
        position = Position.create_csp(
            symbol=symbol,
            strike=float(strike),
            expiry=expiry[:10],
            contracts=contracts,
            premium_collected=entry_credit,
            notes=notes,
        )
        position.entry_date = open_date + "T12:00:00+00:00"
        position.open_date = open_date

    store.insert_position(position)
    add_position_event(position.id, "OPENED", {"source": "manual", "notes": notes})
    add_capital_ledger_entry(open_date, position.id, "OPEN", entry_credit, notes)
    return position


def update_position_notes(position_id: str, notes: str) -> None:
    """Update notes for a position and append MANUAL_NOTE event (Phase 6.7)."""
    init_persistence_db()
    store = PositionStore(db_path=get_db_path())
    pos = store.fetch_position_by_id(position_id)
    if not pos:
        raise ValueError(f"Position not found: {position_id}")
    store.update_notes(position_id, notes or "")
    add_position_event(position_id, "MANUAL_NOTE", {"notes": notes or ""})


def record_partial_close(
    position_id: str,
    realized_pnl_delta: float,
    notes: Optional[str] = None,
) -> None:
    """Record a partial close (Phase 6.7). OPEN->PARTIALLY_CLOSED or add PnL if already PARTIALLY_CLOSED.
    Updates realized_pnl, adds TARGET_1_HIT event and ledger PARTIAL_CLOSE."""
    init_persistence_db()
    store = PositionStore(db_path=get_db_path())
    pos = store.fetch_position_by_id(position_id)
    if not pos:
        raise ValueError(f"Position not found: {position_id}")
    from_state = (pos.lifecycle_state or pos.state or "OPEN").strip()
    current_rp = float(getattr(pos, "realized_pnl", None) or 0)
    new_rp = current_rp + float(realized_pnl_delta)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if from_state == "OPEN":
        validate_lifecycle_transition(from_state, "PARTIALLY_CLOSED", position_id)
        store.update_lifecycle_and_pnl(
            position_id,
            "PARTIALLY_CLOSED",
            realized_pnl=new_rp,
            notes=notes if notes is not None else pos.notes,
        )
    else:
        store.update_lifecycle_and_pnl(
            position_id,
            from_state,
            realized_pnl=new_rp,
            notes=notes if notes is not None else pos.notes,
        )
    add_position_event(position_id, "TARGET_1_HIT", {"realized_pnl_delta": realized_pnl_delta, "notes": notes or ""})
    add_capital_ledger_entry(today, position_id, "PARTIAL_CLOSE", float(realized_pnl_delta), notes)


def record_close(
    position_id: str,
    realized_pnl_delta: float,
    notes: Optional[str] = None,
) -> None:
    """Record full close (Phase 6.7). Validates lifecycle->CLOSED, sets close_date, adds CLOSED event and ledger CLOSE."""
    init_persistence_db()
    store = PositionStore(db_path=get_db_path())
    pos = store.fetch_position_by_id(position_id)
    if not pos:
        raise ValueError(f"Position not found: {position_id}")
    from_state = (pos.lifecycle_state or pos.state or "OPEN").strip()
    if from_state == "CLOSED":
        raise InvalidLifecycleTransitionError(position_id, from_state, "CLOSED")
    validate_lifecycle_transition(from_state, "CLOSED", position_id)
    current_rp = float(getattr(pos, "realized_pnl", None) or 0)
    new_rp = current_rp + float(realized_pnl_delta)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    store.update_lifecycle_and_pnl(
        position_id,
        "CLOSED",
        realized_pnl=new_rp,
        close_date=today,
        notes=notes if notes is not None else pos.notes,
    )
    add_position_event(position_id, "CLOSED", {"realized_pnl": new_rp, "notes": notes or ""})
    add_capital_ledger_entry(today, position_id, "CLOSE", float(realized_pnl_delta), notes)


def record_assignment(position_id: str, notes: Optional[str] = None) -> None:
    """Mark position as assigned (Phase 6.7). Validates lifecycle->ASSIGNED, adds ASSIGNED event and ledger ASSIGNMENT 0.0."""
    init_persistence_db()
    store = PositionStore(db_path=get_db_path())
    pos = store.fetch_position_by_id(position_id)
    if not pos:
        raise ValueError(f"Position not found: {position_id}")
    from_state = (pos.lifecycle_state or pos.state or "OPEN").strip()
    validate_lifecycle_transition(from_state, "ASSIGNED", position_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    store.update_lifecycle_and_pnl(
        position_id,
        "ASSIGNED",
        notes=notes if notes is not None else pos.notes,
    )
    add_position_event(position_id, "ASSIGNED", {"notes": notes or ""})
    add_capital_ledger_entry(today, position_id, "ASSIGNMENT", 0.0, notes)


def add_capital_ledger_entry(
    date: str,
    position_id: str,
    event_type: str,
    cash_delta: float,
    notes: Optional[str] = None,
) -> None:
    """Append a capital ledger entry (Phase 6.4). event_type: OPEN, PARTIAL_CLOSE, CLOSE, ASSIGNMENT."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO capital_ledger_entries (date, position_id, event_type, cash_delta, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date, position_id, event_type, float(cash_delta), notes or "", now))
        conn.commit()
    finally:
        conn.close()


def get_capital_ledger_entries(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    position_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return ledger entries in date order (Phase 6.4). Filter by date range and/or position_id."""
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        q = """
            SELECT date, position_id, event_type, cash_delta, notes
            FROM capital_ledger_entries
            WHERE 1=1
        """
        params: List[Any] = []
        if date_from:
            q += " AND date >= ?"
            params.append(date_from)
        if date_to:
            q += " AND date <= ?"
            params.append(date_to)
        if position_id:
            q += " AND position_id = ?"
            params.append(position_id)
        q += " ORDER BY date ASC, id ASC"
        cursor.execute(q, params)
        rows = cursor.fetchall()
        return [
            {"date": r[0], "position_id": r[1], "event_type": r[2], "cash_delta": r[3], "notes": r[4] or ""}
            for r in rows
        ]
    finally:
        conn.close()


def compute_monthly_summary(year: int, month: int) -> MonthlySummary:
    """Compute deterministic monthly summary from ledger + positions (Phase 6.4). Same inputs → same numbers."""
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return MonthlySummary(
            year=year, month=month,
            total_credit_collected=0.0, realized_pnl=0.0, unrealized_pnl=0.0,
            win_rate=0.0, avg_days_in_trade=0.0, max_drawdown=0.0,
        )
    date_from = f"{year:04d}-{month:02d}-01"
    if month == 12:
        date_to = f"{year:04d}-12-31"
    else:
        date_to = f"{year:04d}-{month:02d}-31"  # SQLite/string compare ok for YYYY-MM-DD
    entries = get_capital_ledger_entries(date_from=date_from, date_to=date_to)
    total_credit_collected = sum(e["cash_delta"] for e in entries if e["event_type"] == "OPEN")
    realized_pnl = sum(
        e["cash_delta"] for e in entries
        if e["event_type"] in ("PARTIAL_CLOSE", "CLOSE")
    )
    # Unrealized: from open positions (no mark in DB → 0 for deterministic summary)
    unrealized_pnl = 0.0
    # Win rate and avg_days from positions that closed this month (from ledger CLOSE entries)
    close_entries = [e for e in entries if e["event_type"] == "CLOSE"]
    closed_ids = {e["position_id"] for e in close_entries}
    closed_positions: List[Any] = []
    if closed_ids:
        conn2 = sqlite3.connect(str(db_path))
        cur = conn2.cursor()
        try:
            placeholders = ",".join("?" * len(closed_ids))
            cur.execute(f"""
                SELECT id, symbol, position_type, strike, expiry, contracts, premium_collected,
                       entry_date, status, state, state_history, notes, exit_plan,
                       entry_credit, open_date, close_date, realized_pnl, lifecycle_state
                FROM positions
                WHERE id IN ({placeholders})
            """, list(closed_ids))
            rows = cur.fetchall()
            for row in rows:
                p = PositionStore(db_path=db_path)._row_to_position(row)
                closed_positions.append(p)
        except Exception:
            pass
        finally:
            conn2.close()
    wins = 0
    total_closes = len(close_entries)
    days_list: List[float] = []
    for p in closed_positions:
        rp = getattr(p, "realized_pnl", None)
        if rp is not None and rp > 0:
            wins += 1
        od = getattr(p, "open_date", None) or (p.entry_date[:10] if getattr(p, "entry_date", None) else None)
        cd = getattr(p, "close_date", None)
        if od and cd:
            try:
                from datetime import datetime as dt
                d1 = dt.strptime(od, "%Y-%m-%d")
                d2 = dt.strptime(cd, "%Y-%m-%d")
                days_list.append((d2 - d1).days)
            except (ValueError, TypeError):
                pass
    win_rate = (wins / total_closes) if total_closes else 0.0
    avg_days_in_trade = (sum(days_list) / len(days_list)) if days_list else 0.0
    # Simple max drawdown: cumulative pnl then peak-to-trough
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for e in entries:
        if e["event_type"] == "OPEN":
            cum += e["cash_delta"]
        elif e["event_type"] in ("PARTIAL_CLOSE", "CLOSE"):
            cum += e["cash_delta"]
        elif e["event_type"] == "ASSIGNMENT":
            cum += e["cash_delta"]
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return MonthlySummary(
        year=year,
        month=month,
        total_credit_collected=round(total_credit_collected, 2),
        realized_pnl=round(realized_pnl, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        win_rate=round(win_rate, 4),
        avg_days_in_trade=round(avg_days_in_trade, 2),
        max_drawdown=round(max_dd, 2),
    )


def get_capital_deployed_today() -> float:
    """Sum of OPEN cash_delta for today (Phase 6.4 trust report)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries = get_capital_ledger_entries(date_from=today, date_to=today)
    return sum(e["cash_delta"] for e in entries if e["event_type"] == "OPEN")


def get_mtd_realized_pnl() -> float:
    """Month-to-date realized pnl from ledger (Phase 6.4 trust report)."""
    now = datetime.now(timezone.utc)
    date_from = f"{now.year:04d}-{now.month:02d}-01"
    date_to = now.strftime("%Y-%m-%d")
    entries = get_capital_ledger_entries(date_from=date_from, date_to=date_to)
    return sum(
        e["cash_delta"] for e in entries
        if e["event_type"] in ("PARTIAL_CLOSE", "CLOSE")
    )


def save_decision_artifact_metadata(decision_ts: str, meta_json: str) -> None:
    """Store decision artifact metadata for UI read models (Phase 6.5). Upserts by decision_ts."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO decision_artifacts_meta (decision_ts, meta_json, created_at)
            VALUES (?, ?, ?)
        """, (decision_ts, meta_json, now))
        conn.commit()
    finally:
        conn.close()


def get_latest_decision_artifact_metadata() -> Optional[Dict[str, Any]]:
    """Best-effort: latest decision meta for DailyOverviewView (Phase 6.5). Returns None if none stored."""
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT decision_ts, meta_json FROM decision_artifacts_meta ORDER BY decision_ts DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        meta = json.loads(row[1]) if row[1] else {}
        meta["decision_ts"] = row[0]
        return meta
    except (json.JSONDecodeError, TypeError):
        return None
    finally:
        conn.close()


def get_latest_daily_trust_report(days_back: int = 2) -> Optional[Dict[str, Any]]:
    """Latest daily trust report from DB (Phase 6.5). Returns most recent report or None."""
    history = get_trust_report_history("daily", max(1, days_back))
    return history[0] if history else None


def get_positions_for_view(
    states: Optional[tuple] = None,
) -> List[Position]:
    """Positions for UI view; filter by lifecycle_state (Phase 6.5). Default: OPEN, PARTIALLY_CLOSED, CLOSED, ASSIGNED."""
    if states is None:
        states = ("OPEN", "PARTIALLY_CLOSED", "CLOSED", "ASSIGNED")
    store = PositionStore(db_path=get_db_path())
    return store.fetch_positions_by_lifecycle_states(list(states))


def get_position_events_for_view(position_id: str) -> List[Dict[str, Any]]:
    """Position events for UI (Phase 6.5). Same as get_position_history."""
    return get_position_history(position_id)


def get_recent_position_events(days: int = 7) -> List[Dict[str, Any]]:
    """Position events in the last N days for AlertsView (Phase 6.5)."""
    init_persistence_db()
    db_path = get_db_path()
    if not db_path.exists():
        return []
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT position_id, event_type, event_time, metadata
            FROM position_events WHERE event_time >= ? ORDER BY event_time DESC
        """, (since,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            pos_id, ev_type, ev_time, meta_str = row
            meta = {}
            if meta_str:
                try:
                    meta = json.loads(meta_str)
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append({
                "position_id": pos_id,
                "event_type": ev_type,
                "event_time": ev_time,
                "metadata": meta,
            })
        return result
    finally:
        conn.close()


def get_monthly_summaries(last_n: int = 3) -> List[Dict[str, Any]]:
    """Last N months of MonthlySummary as dicts (Phase 6.5)."""
    now = datetime.now(timezone.utc)
    result = []
    for i in range(last_n):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        summary = compute_monthly_summary(y, m)
        result.append({
            "year": summary.year,
            "month": summary.month,
            "total_credit_collected": summary.total_credit_collected,
            "realized_pnl": summary.realized_pnl,
            "unrealized_pnl": summary.unrealized_pnl,
            "win_rate": summary.win_rate,
            "avg_days_in_trade": summary.avg_days_in_trade,
            "max_drawdown": summary.max_drawdown,
        })
    return result


def get_latest_trade_proposal_view(
    symbol: Optional[str] = None,
    decision_ts: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Trade proposal dict for TradePlanView (Phase 6.5). Reuses existing accessors."""
    if decision_ts:
        return get_trade_proposal_by_decision_ts(decision_ts)
    return get_latest_trade_proposal(symbol=symbol)


def get_trade_proposal_by_decision_ts(decision_ts: str) -> Optional[Dict[str, Any]]:
    """Get trade proposal row by decision_ts (for dashboard to merge ack state). Returns full row with id."""
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, proposal_json, execution_status, user_acknowledged, execution_notes, skipped
            FROM trade_proposals WHERE decision_ts = ? ORDER BY id DESC LIMIT 1
        """, (decision_ts,))
        row = cursor.fetchone()
        if not row:
            return None
        proposal_data = json.loads(row[1])
        proposal_data["_id"] = row[0]
        proposal_data["execution_status"] = row[2]
        proposal_data["user_acknowledged"] = bool(row[3])
        proposal_data["execution_notes"] = row[4] or ""
        proposal_data["skipped"] = bool(row[5])
        return proposal_data
    finally:
        conn.close()


def initialize_schema() -> None:
    """Initialize all required SQLite tables on startup.
    
    This function ensures all tables exist with correct schema before any
    SELECT/INSERT operations. Called automatically on module import.
    
    Creates tables:
    - market_snapshots: Snapshot metadata
    - market_snapshot_data: Per-symbol snapshot data
    - symbol_universe: Enabled/disabled symbols
    - market_regimes: Market regime tracking
    - csp_evaluations: CSP candidate evaluation results
    - alerts: Alert lifecycle management
    """
    db_path = DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # market_snapshots (Phase 2A)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                snapshot_timestamp_et TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'snapshot',
                symbol_count INTEGER NOT NULL,
                data_age_minutes REAL NOT NULL,
                is_frozen INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        
        # market_snapshot_data (Phase 2A)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshot_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                data_json TEXT,
                has_data INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(snapshot_id, symbol)
            )
        """)
        
        # symbol_universe (Phase 1A.1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbol_universe (
                symbol TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # market_regimes (Phase 2B Step 1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_regimes (
                snapshot_id TEXT PRIMARY KEY,
                regime TEXT NOT NULL,
                benchmark_symbol TEXT,
                benchmark_return REAL,
                computed_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # csp_evaluations (Phase 2B Step 2)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS csp_evaluations (
                snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                eligible INTEGER NOT NULL,
                score INTEGER NOT NULL,
                reasons_json TEXT,
                features_json TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (snapshot_id, symbol)
            )
        """)
        
        # alerts (Phase 1A.1) - ensure it has status column
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                level TEXT NOT NULL,
                status TEXT DEFAULT 'OPEN',
                created_at TEXT NOT NULL
            )
        """)
        
        # Add status column if it doesn't exist (migration)
        try:
            cursor.execute("ALTER TABLE alerts ADD COLUMN status TEXT DEFAULT 'OPEN'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Migrate existing alerts to OPEN status
        cursor.execute("""
            UPDATE alerts SET status = 'OPEN' WHERE status IS NULL
        """)
        
        # Phase 4.3: trade_proposals (execution readiness and human acknowledgment)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                proposal_json TEXT NOT NULL,
                execution_status TEXT NOT NULL,
                user_acknowledged INTEGER NOT NULL DEFAULT 0,
                execution_notes TEXT DEFAULT '',
                skipped INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_timestamp ON market_snapshots(snapshot_timestamp_et DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_data_symbol ON market_snapshot_data(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_data_snapshot ON market_snapshot_data(snapshot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_universe_enabled ON symbol_universe(enabled)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_regimes_computed_at ON market_regimes(computed_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_csp_eval_snapshot ON csp_evaluations(snapshot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_csp_eval_eligible ON csp_evaluations(eligible, score DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_csp_eval_symbol ON csp_evaluations(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_proposals_decision_ts ON trade_proposals(decision_ts DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_proposals_symbol ON trade_proposals(symbol)")
        
        # Phase 5.2: rejection_daily_summary
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rejection_daily_summary (
                date TEXT PRIMARY KEY,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejection_daily_date ON rejection_daily_summary(date DESC)")
        
        conn.commit()
        logger.info("[DB INIT] Schema initialization complete")
        logger.info("[DB INIT] csp_evaluations schema verified")
    except Exception as e:
        logger.error(f"[DB INIT] Failed to initialize schema: {e}")
        raise
    finally:
        conn.close()


# Initialize schema on module import (guarded to run once)
_schema_initialized = False
if not _schema_initialized:
    try:
        initialize_schema()
        _schema_initialized = True
    except Exception as e:
        logger.warning(f"[DB INIT] Schema initialization failed on import: {e}")


__all__ = [
    "init_persistence_db",
    "initialize_schema",
    "record_trade",
    "upsert_position_from_trade",
    "recompute_positions",
    "list_open_positions",
    "mark_candidate_executed",
    "list_candidates",
    "create_alert",
    "list_alerts",
    "ack_alert",
    "archive_alert",
    "bulk_ack_alerts",
    "bulk_archive_non_action_alerts",
    "save_portfolio_snapshot",
    "get_latest_portfolio_snapshot",
    "get_enabled_symbols",
    "get_all_symbols",
    "list_universe_symbols",
    "add_symbol",
    "update_symbol",
    "toggle_symbol",
    "delete_symbol",
    "add_universe_symbol",
    "toggle_universe_symbol",
    "delete_universe_symbol",
    "reset_local_trading_state",
    "save_assignment_profile",
    "get_assignment_profile",
    "set_assignment_override",
    "is_assignment_blocked",
    "upsert_regime",
    "get_latest_regime",
    "upsert_csp_evaluations",
    "get_csp_evaluations",
    "get_rejection_reason_counts",
    "save_trade_proposal",
    "get_latest_trade_proposal",
    "update_trade_proposal_acknowledgment",
    "get_trade_proposal_by_decision_ts",
    "save_daily_rejection_summary",
    "get_rejection_history",
    "save_trust_report",
    "get_trust_report_history",
    "save_config_freeze_state",
    "get_config_freeze_state",
    "get_daily_run_cycle",
    "start_daily_run_cycle",
    "update_daily_run_cycle_phase",
    "set_daily_run_cycle_complete",
    "add_position_event",
    "get_position_history",
    "get_position_by_id",
    "create_manual_position",
    "update_position_notes",
    "record_partial_close",
    "record_close",
    "record_assignment",
    "add_capital_ledger_entry",
    "get_capital_ledger_entries",
    "compute_monthly_summary",
    "get_capital_deployed_today",
    "get_mtd_realized_pnl",
    "save_decision_artifact_metadata",
    "get_latest_decision_artifact_metadata",
    "get_latest_daily_trust_report",
    "get_positions_for_view",
    "get_position_events_for_view",
    "get_recent_position_events",
    "get_monthly_summaries",
    "get_latest_trade_proposal_view",
]
