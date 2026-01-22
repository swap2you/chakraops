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
from app.db.database import get_db_path


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
    - Updates csp_candidates with executed flag
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
        
        # Update alerts table: add status column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE alerts ADD COLUMN status TEXT DEFAULT 'OPEN'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Migrate existing alerts to OPEN status
        cursor.execute("""
            UPDATE alerts SET status = 'OPEN' WHERE status IS NULL
        """)
        
        # Update csp_candidates table: add executed flag if it doesn't exist
        try:
            cursor.execute("ALTER TABLE csp_candidates ADD COLUMN executed INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_executed ON csp_candidates(executed)")
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
        
        conn.commit()
    except Exception as e:
        # Log clear error if schema init fails
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to initialize persistence database: {e}")
        raise
    finally:
        conn.close()


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
                # Update in database
                cursor.execute("""
                    UPDATE positions
                    SET status = 'CLOSED', state = 'CLOSED'
                    WHERE id = ?
                """, (position.id,))
                conn.commit()
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
                # Update in database
                cursor.execute("""
                    UPDATE positions
                    SET status = 'ASSIGNED', state = 'ASSIGNED'
                    WHERE id = ?
                """, (position.id,))
                conn.commit()
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
    """Mark a CSP candidate as executed.
    
    Parameters
    ----------
    symbol:
        Stock symbol to mark.
    executed:
        True to mark as executed, False to unmark.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE csp_candidates
            SET executed = ?
            WHERE symbol = ?
        """, (1 if executed else 0, symbol.upper()))
        conn.commit()
    finally:
        conn.close()


def list_candidates(include_executed: bool = False) -> List[Dict[str, Any]]:
    """List CSP candidates, optionally filtering executed ones.
    
    Parameters
    ----------
    include_executed:
        If False, exclude executed candidates.
    
    Returns
    -------
    List[Dict[str, Any]]
        List of candidate dictionaries.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return []
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        if include_executed:
            cursor.execute("""
                SELECT symbol, score, reasons, key_levels, created_at, executed
                FROM csp_candidates
                ORDER BY score DESC, created_at DESC
            """)
        else:
            cursor.execute("""
                SELECT symbol, score, reasons, key_levels, created_at, executed
                FROM csp_candidates
                WHERE executed = 0 OR executed IS NULL
                ORDER BY score DESC, created_at DESC
            """)
        
        rows = cursor.fetchall()
        candidates = []
        for row in rows:
            candidates.append({
                "symbol": row[0],
                "score": row[1],
                "reasons": json.loads(row[2]) if row[2] else [],
                "key_levels": json.loads(row[3]) if row[3] else {},
                "created_at": row[4],
                "executed": bool(row[5]) if len(row) > 5 else False,
            })
        return candidates
    finally:
        conn.close()


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
    """
    symbols = list_universe_symbols()
    return [row["symbol"] for row in symbols if row.get("enabled")]


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


def add_universe_symbol(symbol: str, enabled: bool = True, notes: Optional[str] = None) -> None:
    """Add or update a symbol in the universe.
    
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


def toggle_universe_symbol(symbol: str, enabled: bool) -> None:
    """Toggle enabled status of a symbol.
    
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


def delete_universe_symbol(symbol: str) -> None:
    """Delete a symbol from the universe.
    
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


__all__ = [
    "init_persistence_db",
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
    "list_universe_symbols",
    "add_universe_symbol",
    "toggle_universe_symbol",
    "delete_universe_symbol",
    "reset_local_trading_state",
    "save_assignment_profile",
    "get_assignment_profile",
    "set_assignment_override",
    "is_assignment_blocked",
]
