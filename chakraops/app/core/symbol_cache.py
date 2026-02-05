# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Symbol cache management for ThetaData symbols (Phase 1B.2).

This module provides:
- Fetching all tradable symbols from ThetaData
- Caching symbols locally in database
- Fast symbol search for UI
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import sqlite3

from app.core.persistence import get_db_path, init_persistence_db

logger = logging.getLogger(__name__)


def fetch_and_cache_theta_symbols() -> int:
    """Fetch all tradable symbols from ThetaData and cache them.
    
    This is a one-time operation that caches symbols locally.
    Subsequent calls check cache first.
    
    Returns
    -------
    int
        Number of symbols cached.
    
    Raises
    ------
    RuntimeError
        If ThetaData is not available or fetch fails.
    """
    init_persistence_db()
    db_path = get_db_path()
    
    # Check if cache already exists and is recent (within 7 days)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM symbol_cache")
        count = cursor.fetchone()[0]
        
        if count > 0:
            # Cache exists, check if it's recent
            cursor.execute("SELECT MAX(cached_at) FROM symbol_cache")
            max_date = cursor.fetchone()[0]
            if max_date:
                from datetime import datetime as dt
                cached_time = dt.fromisoformat(max_date)
                age_days = (dt.now(timezone.utc) - cached_time.replace(tzinfo=timezone.utc)).days
                if age_days < 7:
                    logger.info(f"Symbol cache is recent ({age_days} days old), skipping refresh")
                    return count
    except sqlite3.OperationalError:
        # Table doesn't exist yet, will be created below
        pass
    finally:
        conn.close()
    
    # Fetch symbols from ThetaData
    try:
        from app.core.market_data.thetadata_provider import ThetaDataProvider
        
        provider = ThetaDataProvider()
        
        # ThetaData endpoint: /stock/list/symbols
        # Returns list of symbols with format: [{"symbol": "AAPL", "name": "Apple Inc.", ...}, ...]
        response = provider._make_request("/stock/list/symbols", format="json")
        
        if not response:
            raise RuntimeError("ThetaData returned empty symbol list")
        
        # Handle different response formats
        if isinstance(response, dict):
            # If wrapped in a dict, try to extract list
            if "response" in response:
                response = response["response"]
            elif "data" in response:
                response = response["data"]
            else:
                raise RuntimeError("ThetaData returned unexpected response format")
        
        if not isinstance(response, list):
            raise RuntimeError("ThetaData returned invalid symbol list format (not a list)")
        
    except ImportError:
        raise RuntimeError("ThetaData provider not available")
    except Exception as e:
        logger.error(f"Failed to fetch symbols from ThetaData: {e}")
        raise RuntimeError(f"Failed to fetch symbols from ThetaData: {e}") from e
    
    # Store in cache
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbol_cache (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                exchange TEXT,
                cached_at TEXT NOT NULL
            )
        """)
        
        # Clear old cache
        cursor.execute("DELETE FROM symbol_cache")
        
        # Insert new symbols
        cached_at = datetime.now(timezone.utc).isoformat()
        symbols_cached = 0
        
        for item in response:
            if isinstance(item, dict):
                symbol = item.get("symbol", "").upper()
                if symbol:
                    name = item.get("name", "")
                    exchange = item.get("exchange", "")
                    
                    cursor.execute("""
                        INSERT INTO symbol_cache (symbol, name, exchange, cached_at)
                        VALUES (?, ?, ?, ?)
                    """, (symbol, name, exchange, cached_at))
                    symbols_cached += 1
            elif isinstance(item, str):
                # Handle case where response is just a list of symbol strings
                symbol = item.upper()
                if symbol:
                    cursor.execute("""
                        INSERT INTO symbol_cache (symbol, name, exchange, cached_at)
                        VALUES (?, ?, ?, ?)
                    """, (symbol, None, None, cached_at))
                    symbols_cached += 1
        
        conn.commit()
        logger.info(f"Cached {symbols_cached} symbols from ThetaData")
        return symbols_cached
    
    finally:
        conn.close()


def search_symbols(query: str, limit: int = 50) -> List[Dict[str, str]]:
    """Search symbols in cache by partial match (case-insensitive).
    
    Parameters
    ----------
    query:
        Search query (1-2 chars minimum for performance).
    limit:
        Maximum number of results to return (default: 50).
    
    Returns
    -------
    List[Dict[str, str]]
        List of symbol dictionaries with symbol, name, exchange.
    """
    if not query or len(query) < 1:
        return []
    
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbol_cache (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                exchange TEXT,
                cached_at TEXT NOT NULL
            )
        """)
        
        # Case-insensitive search
        query_upper = query.upper()
        cursor.execute("""
            SELECT symbol, name, exchange
            FROM symbol_cache
            WHERE symbol LIKE ? OR (name IS NOT NULL AND name LIKE ?)
            ORDER BY symbol
            LIMIT ?
        """, (f"%{query_upper}%", f"%{query}%", limit))
        
        rows = cursor.fetchall()
        return [
            {
                "symbol": row[0],
                "name": row[1] or "",
                "exchange": row[2] or "",
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_cached_symbol_count() -> int:
    """Get count of cached symbols.
    
    Returns
    -------
    int
        Number of symbols in cache, or 0 if cache doesn't exist.
    """
    init_persistence_db()
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM symbol_cache")
        return cursor.fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


__all__ = [
    "fetch_and_cache_theta_symbols",
    "search_symbols",
    "get_cached_symbol_count",
]
