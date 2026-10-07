#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""SQLite-backed storage for ChakraOps positions.

This module provides a thin, typed wrapper around ``sqlite3`` for persisting
and retrieving :class:`app.core.models.position.Position` objects.

Responsibilities only cover storage concerns:
- Database/file initialization
- Basic CRUD-style operations for positions

All trading and risk logic lives elsewhere.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from app.core.models.position import Position, PositionStatus
from app.core.config.paths import DB_PATH
from app.models.exit_plan import exit_plan_from_dict, exit_plan_to_dict, get_default_exit_plan


class PositionStore:
    """Persistence layer for :class:`Position` objects using SQLite."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Create a new ``PositionStore``.

        Parameters
        ----------
        db_path:
            Path to the SQLite database file. If omitted, uses the canonical
            DB_PATH from app.core.config (app/data/chakraops.db).
        """
        if db_path is None:
            db_path = DB_PATH

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _get_connection(self) -> sqlite3.Connection:
        """Open a new SQLite connection."""
        conn = sqlite3.connect(str(self.db_path))
        return conn

    def _init_db(self) -> None:
        """Initialize the database schema if it does not exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    position_type TEXT NOT NULL,
                    strike REAL,
                    expiry TEXT,
                    contracts INTEGER NOT NULL,
                    premium_collected REAL NOT NULL,
                    entry_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state TEXT,
                    state_history TEXT,
                    notes TEXT,
                    exit_plan TEXT
                )
                """
            )
            conn.commit()
            
            # Migrate existing data: add state and state_history columns if they don't exist
            try:
                cursor.execute("ALTER TABLE positions ADD COLUMN state TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                cursor.execute("ALTER TABLE positions ADD COLUMN state_history TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE positions ADD COLUMN exit_plan TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Migrate existing positions: set state from status if state is NULL
            cursor.execute("""
                UPDATE positions
                SET state = CASE
                    WHEN status = 'OPEN' THEN 'OPEN'
                    WHEN status = 'ASSIGNED' THEN 'ASSIGNED'
                    WHEN status = 'CLOSED' THEN 'CLOSED'
                    ELSE 'OPEN'
                END
                WHERE state IS NULL
            """)
            
            # Initialize empty state_history for positions that don't have it
            cursor.execute("""
                UPDATE positions
                SET state_history = '[]'
                WHERE state_history IS NULL
            """)

            # Phase 6.3: position lifecycle and PnL columns
            for col, typ in [
                ("entry_credit", "REAL"),
                ("open_date", "TEXT"),
                ("close_date", "TEXT"),
                ("realized_pnl", "REAL"),
                ("lifecycle_state", "TEXT"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE positions ADD COLUMN {col} {typ}")
                except sqlite3.OperationalError:
                    pass  # Column already exists
            cursor.execute("""
                UPDATE positions SET lifecycle_state = state WHERE lifecycle_state IS NULL
            """)
            cursor.execute("""
                UPDATE positions SET entry_credit = premium_collected WHERE entry_credit IS NULL
            """)
            cursor.execute("""
                UPDATE positions SET open_date = substr(entry_date, 1, 10) WHERE open_date IS NULL AND entry_date IS NOT NULL
            """)
            cursor.execute("""
                UPDATE positions SET realized_pnl = 0 WHERE realized_pnl IS NULL
            """)
            
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def insert_position(self, position: Position) -> None:
        """Insert a new position into the database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get state (default to status if state not set)
            state = position.state or (position.status if hasattr(position, 'status') else 'OPEN')
            
            # Serialize state_history to JSON
            state_history_json = json.dumps([
                {
                    'from_state': event.from_state if hasattr(event, 'from_state') else event.get('from_state'),
                    'to_state': event.to_state if hasattr(event, 'to_state') else event.get('to_state'),
                    'reason': event.reason if hasattr(event, 'reason') else event.get('reason'),
                    'source': event.source if hasattr(event, 'source') else event.get('source'),
                    'timestamp_iso': event.timestamp_iso if hasattr(event, 'timestamp_iso') else event.get('timestamp_iso'),
                }
                for event in (position.state_history or [])
            ])
            
            exit_plan_json = None
            if getattr(position, 'exit_plan', None) is not None:
                exit_plan_json = json.dumps(exit_plan_to_dict(position.exit_plan))

            entry_credit = getattr(position, 'entry_credit', None) or position.premium_collected
            open_date = getattr(position, 'open_date', None) or (position.entry_date[:10] if position.entry_date else None)
            close_date = getattr(position, 'close_date', None)
            realized_pnl = getattr(position, 'realized_pnl', None)
            if realized_pnl is None:
                realized_pnl = 0.0
            lifecycle_state = getattr(position, 'lifecycle_state', None) or state

            cursor.execute(
                """
                INSERT INTO positions (
                    id, symbol, position_type, strike, expiry,
                    contracts, premium_collected, entry_date,
                    status, state, state_history, notes, exit_plan,
                    entry_credit, open_date, close_date, realized_pnl, lifecycle_state
                )
                VALUES (
                    :id, :symbol, :position_type, :strike, :expiry,
                    :contracts, :premium_collected, :entry_date,
                    :status, :state, :state_history, :notes, :exit_plan,
                    :entry_credit, :open_date, :close_date, :realized_pnl, :lifecycle_state
                )
                """,
                {
                    'id': position.id,
                    'symbol': position.symbol,
                    'position_type': position.position_type,
                    'strike': position.strike,
                    'expiry': position.expiry,
                    'contracts': position.contracts,
                    'premium_collected': position.premium_collected,
                    'entry_date': position.entry_date,
                    'status': position.status,
                    'state': state,
                    'state_history': state_history_json,
                    'notes': position.notes,
                    'exit_plan': exit_plan_json,
                    'entry_credit': entry_credit,
                    'open_date': open_date,
                    'close_date': close_date,
                    'realized_pnl': realized_pnl,
                    'lifecycle_state': lifecycle_state,
                },
            )
            conn.commit()
        finally:
            conn.close()

    def fetch_all_open_positions(self) -> List[Position]:
        """Fetch all positions with status ``\"OPEN\"`` or state in OPEN/HOLD/ROLL_CANDIDATE/ROLLING."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id, symbol, position_type, strike, expiry,
                    contracts, premium_collected, entry_date,
                    status, state, state_history, notes, exit_plan
                FROM positions
                WHERE status = 'OPEN' OR state IN ('OPEN', 'HOLD', 'ROLL_CANDIDATE', 'ROLLING')
                ORDER BY entry_date DESC
                """
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [self._row_to_position(row) for row in rows]

    def fetch_positions_by_lifecycle_states(
        self, states: Optional[List[str]] = None
    ) -> List[Position]:
        """Fetch positions whose lifecycle_state is in the given list (Phase 6.5).
        Default: OPEN, PARTIALLY_CLOSED, CLOSED, ASSIGNED (all).
        """
        if states is None:
            states = ["OPEN", "PARTIALLY_CLOSED", "CLOSED", "ASSIGNED"]
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(states))
            cursor.execute(
                f"""
                SELECT
                    id, symbol, position_type, strike, expiry,
                    contracts, premium_collected, entry_date,
                    status, state, state_history, notes, exit_plan,
                    entry_credit, open_date, close_date, realized_pnl, lifecycle_state
                FROM positions
                WHERE lifecycle_state IN ({placeholders})
                ORDER BY entry_date DESC
                """,
                states,
            )
            rows = cursor.fetchall()
        finally:
            conn.close()
        return [self._row_to_position(row) for row in rows]

    def fetch_positions_by_symbol(self, symbol: str) -> List[Position]:
        """Fetch all positions for a given symbol (any status)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id, symbol, position_type, strike, expiry,
                    contracts, premium_collected, entry_date,
                    status, state, state_history, notes, exit_plan,
                    entry_credit, open_date, close_date, realized_pnl, lifecycle_state
                FROM positions
                WHERE symbol = ?
                ORDER BY entry_date DESC
                """,
                (symbol.upper(),),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [self._row_to_position(row) for row in rows]

    def fetch_position_by_id(self, position_id: str) -> Optional[Position]:
        """Fetch a single position by id (Phase 6.7). Returns None if not found."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id, symbol, position_type, strike, expiry,
                    contracts, premium_collected, entry_date,
                    status, state, state_history, notes, exit_plan,
                    entry_credit, open_date, close_date, realized_pnl, lifecycle_state
                FROM positions
                WHERE id = ?
                """,
                (position_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_position(row)
        finally:
            conn.close()

    def update_notes(self, position_id: str, notes: str) -> None:
        """Update notes for a position (Phase 6.7)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE positions SET notes = ? WHERE id = ?",
                (notes or "", position_id),
            )
            conn.commit()
        finally:
            conn.close()

    def update_lifecycle_and_pnl(
        self,
        position_id: str,
        lifecycle_state: str,
        realized_pnl: Optional[float] = None,
        close_date: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Update lifecycle_state, and optionally realized_pnl, close_date, notes (Phase 6.7)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            updates = ["lifecycle_state = ?", "status = ?"]
            params: List[Any] = [lifecycle_state, lifecycle_state]
            if realized_pnl is not None:
                updates.append("realized_pnl = ?")
                params.append(float(realized_pnl))
            if close_date is not None:
                updates.append("close_date = ?")
                params.append(close_date)
            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)
            params.append(position_id)
            cursor.execute(
                f"UPDATE positions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
        finally:
            conn.close()

    def update_position_status(
        self,
        position_id: str,
        status: PositionStatus,
        action: str | None = None,
    ) -> None:
        """Update the status of an existing position.
        
        Parameters
        ----------
        position_id:
            ID of the position to update.
        status:
            New status value (for backward compatibility).
        action:
            Optional action being performed (for state machine validation).
            If provided, state machine validation will be enforced.
        """
        conn = self._get_connection()
        try:
            # If action is provided, enforce state machine
            if action:
                # Fetch current position to get current state
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT state, symbol FROM positions WHERE id = ?
                    """,
                    (position_id,),
                )
                row = cursor.fetchone()
                
                if row:
                    current_state_str, symbol = row[0], row[1]
                    
                    # Convert to PositionState enum
                    from app.core.state_machine import PositionState, PositionAction, validate_transition, next_state
                    
                    # Map string to PositionState
                    state_mapping = {
                        "NEW": PositionState.NEW,
                        "ASSIGNED": PositionState.ASSIGNED,
                        "OPEN": PositionState.OPEN,
                        "ROLLING": PositionState.ROLLING,
                        "CLOSING": PositionState.CLOSING,
                        "CLOSED": PositionState.CLOSED,
                    }
                    current_state = state_mapping.get(current_state_str or "OPEN", PositionState.OPEN)
                    
                    # Map action string to PositionAction
                    action_mapping = {
                        "ASSIGN": PositionAction.ASSIGN,
                        "OPEN": PositionAction.OPEN,
                        "HOLD": PositionAction.HOLD,
                        "ROLL": PositionAction.ROLL,
                        "CLOSE": PositionAction.CLOSE,
                    }
                    position_action = action_mapping.get(action.upper())
                    
                    if position_action:
                        # Get next state from state machine
                        next_state_value = next_state(current_state, position_action)
                        
                        # Validate transition
                        correlation_id = f"update-{position_id}-{datetime.now(timezone.utc).isoformat()}"
                        validate_transition(
                            symbol or position_id,
                            current_state,
                            position_action,
                            next_state_value,
                            correlation_id=correlation_id,
                        )
                        
                        # Update state in database
                        cursor.execute(
                            """
                            UPDATE positions
                            SET state = ?, status = ?
                            WHERE id = ?
                            """,
                            (next_state_value.value, status, position_id),
                        )
                    else:
                        # Unknown action, just update status (backward compatibility)
                        cursor.execute(
                            """
                            UPDATE positions
                            SET status = ?
                            WHERE id = ?
                            """,
                            (status, position_id),
                        )
                else:
                    # Position not found, just update status
                    cursor.execute(
                        """
                        UPDATE positions
                        SET status = ?
                        WHERE id = ?
                        """,
                        (status, position_id),
                    )
            else:
                # No action provided, just update status (backward compatibility)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE positions
                    SET status = ?
                    WHERE id = ?
                    """,
                    (status, position_id),
                )
            
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Row conversion helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_position(row: tuple) -> Position:
        """Convert a SQLite row into a :class:`Position` instance."""
        # Handle old (10), mid (12), new (13 with exit_plan), Phase 6.3 (18 with lifecycle) schema
        entry_credit = None
        open_date = None
        close_date = None
        realized_pnl = None
        lifecycle_state = None
        if len(row) == 10:
            (
                id_,
                symbol,
                position_type,
                strike,
                expiry,
                contracts,
                premium_collected,
                entry_date,
                status,
                notes,
            ) = row
            state = None
            state_history_str = None
            exit_plan_str = None
        elif len(row) == 12:
            (
                id_,
                symbol,
                position_type,
                strike,
                expiry,
                contracts,
                premium_collected,
                entry_date,
                status,
                state,
                state_history_str,
                notes,
            ) = row
            exit_plan_str = None
        elif len(row) >= 18:
            (
                id_,
                symbol,
                position_type,
                strike,
                expiry,
                contracts,
                premium_collected,
                entry_date,
                status,
                state,
                state_history_str,
                notes,
                exit_plan_str,
                entry_credit,
                open_date,
                close_date,
                realized_pnl,
                lifecycle_state,
            ) = row[0:18]
        else:
            (
                id_,
                symbol,
                position_type,
                strike,
                expiry,
                contracts,
                premium_collected,
                entry_date,
                status,
                state,
                state_history_str,
                notes,
                exit_plan_str,
            ) = row

        # Parse state_history from JSON
        state_history = []
        if state_history_str:
            try:
                state_history = json.loads(state_history_str)
            except (json.JSONDecodeError, TypeError):
                state_history = []

        # Parse exit_plan from JSON; default by position_type if missing
        exit_plan = None
        if exit_plan_str:
            try:
                exit_plan = exit_plan_from_dict(json.loads(exit_plan_str))
            except (json.JSONDecodeError, TypeError):
                pass
        if exit_plan is None and position_type == "CSP":
            exit_plan = get_default_exit_plan("CSP")

        # Migrate: if state is None, derive from status
        if state is None:
            status_to_state = {
                "OPEN": "OPEN",
                "ASSIGNED": "ASSIGNED",
                "CLOSED": "CLOSED",
            }
            state = status_to_state.get(status, "OPEN")
        if lifecycle_state is None:
            lifecycle_state = state
        if entry_credit is None:
            entry_credit = premium_collected
        if open_date is None and entry_date:
            try:
                open_date = entry_date[:10]
            except (TypeError, IndexError):
                pass
        if realized_pnl is None:
            realized_pnl = 0.0

        return Position(
            id=id_,
            symbol=symbol,
            position_type=position_type,  # type: ignore[arg-type]
            strike=strike,
            expiry=expiry,
            contracts=contracts,
            premium_collected=premium_collected,
            entry_date=entry_date,
            status=status,  # type: ignore[arg-type]
            state=state,
            state_history=state_history,
            notes=notes,
            exit_plan=exit_plan,
            entry_credit=float(entry_credit) if entry_credit is not None else premium_collected,
            open_date=open_date,
            close_date=close_date,
            realized_pnl=float(realized_pnl) if realized_pnl is not None else 0.0,
            lifecycle_state=lifecycle_state,
        )


__all__ = ["PositionStore"]

