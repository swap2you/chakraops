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

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from app.core.models.position import Position, PositionStatus


class PositionStore:
    """Persistence layer for :class:`Position` objects using SQLite."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Create a new ``PositionStore``.

        Parameters
        ----------
        db_path:
            Path to the SQLite database file. If omitted, defaults to
            ``data/chakra_ops.db`` at the repository root.
        """
        if db_path is None:
            repo_root = Path(__file__).parent.parent.parent
            db_path = repo_root / "data" / "chakra_ops.db"

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
                    notes TEXT
                )
                """
            )
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
            data = asdict(position)
            cursor.execute(
                """
                INSERT INTO positions (
                    id, symbol, position_type, strike, expiry,
                    contracts, premium_collected, entry_date,
                    status, notes
                )
                VALUES (
                    :id, :symbol, :position_type, :strike, :expiry,
                    :contracts, :premium_collected, :entry_date,
                    :status, :notes
                )
                """,
                data,
            )
            conn.commit()
        finally:
            conn.close()

    def fetch_all_open_positions(self) -> List[Position]:
        """Fetch all positions with status ``\"OPEN\"``."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id, symbol, position_type, strike, expiry,
                    contracts, premium_collected, entry_date,
                    status, notes
                FROM positions
                WHERE status = 'OPEN'
                ORDER BY entry_date DESC
                """
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
                    status, notes
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

    def update_position_status(self, position_id: str, status: PositionStatus) -> None:
        """Update the status of an existing position."""
        conn = self._get_connection()
        try:
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
            notes=notes,
        )


__all__ = ["PositionStore"]

