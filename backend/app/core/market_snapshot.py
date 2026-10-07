# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market snapshot management for Phase 2A.

This module provides frozen market snapshot functionality:
- Build snapshot from enabled universe symbols
- Persist snapshot data (one row per symbol)
- Read-only snapshot access (no real-time fetching)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    import pytz
except ImportError:
    pytz = None

from app.core.persistence import get_enabled_symbols, get_db_path
from app.core.market_data.factory import get_market_data_provider

logger = logging.getLogger(__name__)

# ET timezone
_ET_TZ = pytz.timezone("America/New_York") if pytz else None


def normalize_symbol(s: Any) -> str:
    """Canonical symbol normalization: strip and uppercase.
    
    Parameters
    ----------
    s:
        Symbol value (string, or any value that can be converted to string).
    
    Returns
    -------
    str
        Normalized symbol (strip + upper).
    """
    if s is None:
        return ""
    return str(s).strip().upper()


def ensure_et_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is ET timezone-aware."""
    if dt is None:
        return None
    
    if _ET_TZ is None:
        # Fallback: ensure UTC-aware if pytz not available
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    
    # If naive, assume UTC and convert to ET
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to ET
    return dt.astimezone(_ET_TZ)


def parse_snapshot_timestamp(value: Any) -> Optional[datetime]:
    """Parse snapshot timestamp value to timezone-aware datetime (ET preferred).
    
    Handles ISO strings and naive timestamps safely.
    
    Parameters
    ----------
    value:
        Timestamp value (ISO string, datetime, pandas Timestamp, etc.)
    
    Returns
    -------
    Optional[datetime]
        Timezone-aware datetime in ET, or None if parsing fails.
    """
    if value is None:
        return None
    
    try:
        # Handle string (ISO format)
        if isinstance(value, str):
            dt = datetime.fromisoformat(value)
        # Handle pandas Timestamp
        elif hasattr(value, 'to_pydatetime'):
            dt = value.to_pydatetime()
        # Handle datetime
        elif isinstance(value, datetime):
            dt = value
        else:
            # Try to convert to string and parse
            dt = datetime.fromisoformat(str(value))
        
        # Ensure timezone-aware (ET preferred)
        return ensure_et_aware(dt)
    
    except Exception as e:
        logger.warning(f"[SNAPSHOT] Failed to parse timestamp {repr(value)}: {e}")
        return None


def init_snapshot_schema() -> None:
    """Initialize market snapshot table schema."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Create market_snapshots table (metadata)
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
        
        # Create market_snapshot_data table (one row per symbol)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshot_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                data_json TEXT,
                has_data INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (snapshot_id) REFERENCES market_snapshots(snapshot_id),
                UNIQUE(snapshot_id, symbol)
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_timestamp ON market_snapshots(snapshot_timestamp_et DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_data_symbol ON market_snapshot_data(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_data_snapshot ON market_snapshot_data(snapshot_id)")
        
        conn.commit()
    finally:
        conn.close()


def _load_snapshot_from_csv(csv_path: Path) -> Dict[str, Optional[pd.DataFrame]]:
    """Load snapshot data from CSV file.
    
    Expected CSV format (minimum columns):
    - symbol: Stock symbol
    - price: Current price (used as close)
    - timestamp: ISO datetime string or date
    
    Optional columns: open, high, low, volume, iv, delta, dte
    
    Parameters
    ----------
    csv_path:
        Path to CSV file.
    
    Returns
    -------
    Dict[str, Optional[pd.DataFrame]]
        Symbol to DataFrame mapping with columns: date, open, high, low, close, volume
    """
    import pandas as pd
    
    symbol_data_map: Dict[str, Optional[pd.DataFrame]] = {}
    
    try:
        df_csv = pd.read_csv(csv_path)
        
        # Defensive logging: row count
        row_count = len(df_csv)
        logger.info(f"[SNAPSHOT] CSV file loaded: {row_count} rows")
        
        # Validate required columns
        if 'symbol' not in df_csv.columns:
            raise ValueError("CSV must have 'symbol' column")
        
        # Defensive logging: first 3 timestamps
        if 'timestamp' in df_csv.columns and row_count > 0:
            logger.info("[SNAPSHOT] First 3 timestamps from CSV:")
            for idx in range(min(3, row_count)):
                raw_ts = df_csv.iloc[idx]['timestamp']
                parsed_ts = parse_snapshot_timestamp(raw_ts)
                logger.info(f"[SNAPSHOT]   Row {idx}: raw={repr(raw_ts)}, parsed={parsed_ts}")
        elif 'date' in df_csv.columns and row_count > 0:
            logger.info("[SNAPSHOT] First 3 dates from CSV:")
            for idx in range(min(3, row_count)):
                raw_ts = df_csv.iloc[idx]['date']
                parsed_ts = parse_snapshot_timestamp(raw_ts)
                logger.info(f"[SNAPSHOT]   Row {idx}: raw={repr(raw_ts)}, parsed={parsed_ts}")
        
        # DIAGNOSTIC: Log raw CSV symbol values
        raw_symbols = df_csv['symbol'].unique().tolist()
        logger.info(f"[SNAPSHOT DIAG] Raw CSV symbols from pandas: {raw_symbols}")
        logger.info(f"[SNAPSHOT DIAG] Raw CSV symbols (repr): {[repr(s) for s in raw_symbols]}")
        logger.info(f"[SNAPSHOT DIAG] Raw CSV symbols (type): {[type(s).__name__ for s in raw_symbols]}")
        
        # Group by symbol (normalize all symbols)
        normalized_symbol_map: Dict[str, pd.DataFrame] = {}
        for symbol in df_csv['symbol'].unique():
            # Normalize symbol
            normalized_sym = normalize_symbol(symbol)
            if not normalized_sym:
                continue
            
            symbol_rows = df_csv[df_csv['symbol'] == symbol].copy()
            
            if symbol_rows.empty:
                symbol_data_map[symbol] = None
                continue
            
            # Convert to daily OHLCV format expected by system
            # Handle date/timestamp column
            if 'timestamp' in symbol_rows.columns:
                symbol_rows['date'] = pd.to_datetime(symbol_rows['timestamp'])
            elif 'date' in symbol_rows.columns:
                symbol_rows['date'] = pd.to_datetime(symbol_rows['date'])
            else:
                # Use index as fallback
                symbol_rows['date'] = pd.to_datetime('today')
            
            # Handle price/close
            if 'close' in symbol_rows.columns:
                symbol_rows['close'] = symbol_rows['close']
            elif 'price' in symbol_rows.columns:
                symbol_rows['close'] = symbol_rows['price']
            else:
                logger.warning(f"[SNAPSHOT] No price/close column for {symbol}, skipping")
                symbol_data_map[symbol] = None
                continue
            
            # Handle OHLC - use price as default if not available
            symbol_rows['open'] = symbol_rows.get('open', symbol_rows['close'])
            symbol_rows['high'] = symbol_rows.get('high', symbol_rows['close'])
            symbol_rows['low'] = symbol_rows.get('low', symbol_rows['close'])
            symbol_rows['volume'] = symbol_rows.get('volume', 0)
            
            # Phase 2B Step 3: Handle IV rank if present in CSV
            if 'iv_rank' in symbol_rows.columns:
                symbol_rows['iv_rank'] = pd.to_numeric(symbol_rows['iv_rank'], errors='coerce')
            
            # Select and order columns (include iv_rank if present)
            base_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            if 'iv_rank' in symbol_rows.columns:
                base_cols.append('iv_rank')
            df = symbol_rows[base_cols].copy()
            df = df.sort_values('date', ascending=True).reset_index(drop=True)
            
            # Ensure date is datetime
            df['date'] = pd.to_datetime(df['date'])
            
            # Store with normalized symbol key
            normalized_symbol_map[normalized_sym] = df
        
        # Convert to final symbol_data_map
        symbol_data_map = {k: v for k, v in normalized_symbol_map.items()}
        
        symbols_with_data_count = len([s for s in symbol_data_map.values() if s is not None])
        logger.info(
            f"[SNAPSHOT] Loaded {symbols_with_data_count} symbols with data from CSV. "
            f"CSV symbols: {list(symbol_data_map.keys())}"
        )
        return symbol_data_map
    
    except Exception as e:
        logger.error(f"[SNAPSHOT] Failed to load CSV: {e}")
        raise


def _load_snapshot_from_cache() -> Dict[str, Optional[pd.DataFrame]]:
    """Load snapshot data from last known snapshot in DB (CACHE mode).
    
    Returns
    -------
    Dict[str, Optional[pd.DataFrame]]
        Symbol to DataFrame mapping.
    """
    # Get most recent snapshot
    last_snapshot = get_active_snapshot()
    if not last_snapshot:
        return {}
    
    # Load its data
    return load_snapshot_data(last_snapshot["snapshot_id"])


def build_market_snapshot(mode: str = "AUTO") -> Dict[str, Any]:
    """Build a new market snapshot from CSV or CACHE (Phase 2A).
    
    DB Path Unification Fix: Log DB path at snapshot build start.
    """
    # Log DB path at snapshot builder startup
    from app.core.config.paths import DB_PATH
    logger.info(f"[SNAPSHOT] DB_PATH={DB_PATH.absolute()}")
    """Build a frozen market snapshot from enabled universe symbols.
    
    Supports multiple build modes:
    - "CSV": Load from data/snapshots/market_snapshot.csv
    - "CACHE": Load from last known snapshot in DB
    - "AUTO": Try CSV first, then CACHE (never live provider)
    
    Does NOT drop symbols if data is missing - marks missing fields explicitly.
    Does NOT use live market data providers.
    
    Parameters
    ----------
    mode:
        Build mode: "CSV", "CACHE", or "AUTO" (default).
    
    Returns
    -------
    Dict[str, Any]
        Snapshot metadata with:
        - snapshot_id
        - snapshot_timestamp_et
        - provider = "snapshot"
        - symbol_count
        - data_age_minutes
        - is_frozen = True
        - source = "CSV" | "CACHE"
    
    Raises
    ------
    ValueError
        If no snapshot source is available.
    """
    import json
    import pandas as pd
    
    # Initialize schema
    init_snapshot_schema()
    
    # DIAGNOSTIC: Check which table/column is used BEFORE calling get_enabled_symbols()
    from app.core.persistence import get_db_path
    import sqlite3
    db_path = get_db_path()
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        try:
            # 1. Print actual rows from symbol_universe
            logger.info("=" * 80)
            logger.info("[SNAPSHOT DIAG] TASK 1: SELECT symbol, enabled FROM symbol_universe;")
            logger.info("=" * 80)
            cursor.execute("SELECT symbol, enabled FROM symbol_universe ORDER BY symbol")
            universe_rows = cursor.fetchall()
            logger.info(f"[SNAPSHOT DIAG] Raw SQL results: {universe_rows}")
            for row in universe_rows:
                symbol_val = row[0]
                enabled_val = row[1]
                logger.info(f"[SNAPSHOT DIAG]   Row: symbol={repr(symbol_val)} (type={type(symbol_val).__name__}), enabled={enabled_val} (type={type(enabled_val).__name__}, bool={bool(enabled_val)})")
            
            # 2. Print COUNT(*) WHERE enabled = 1
            logger.info("=" * 80)
            logger.info("[SNAPSHOT DIAG] TASK 2: SELECT COUNT(*) FROM symbol_universe WHERE enabled = 1;")
            logger.info("=" * 80)
            cursor.execute("SELECT COUNT(*) FROM symbol_universe WHERE enabled = 1")
            enabled_count = cursor.fetchone()[0]
            logger.info(f"[SNAPSHOT DIAG] COUNT(*) WHERE enabled = 1: {enabled_count}")
            
            # Also show count of all rows
            cursor.execute("SELECT COUNT(*) FROM symbol_universe")
            total_count = cursor.fetchone()[0]
            logger.info(f"[SNAPSHOT DIAG] COUNT(*) total rows: {total_count}")
            
            # 3. Print exact SQL used by get_enabled_symbols()
            logger.info("=" * 80)
            logger.info("[SNAPSHOT DIAG] TASK 3: Exact SQL used by get_enabled_symbols()")
            logger.info("=" * 80)
            logger.info("[SNAPSHOT DIAG] get_enabled_symbols() calls list_universe_symbols() which executes:")
            logger.info("[SNAPSHOT DIAG]   SQL: SELECT symbol, enabled, notes, created_at FROM symbol_universe ORDER BY symbol")
            cursor.execute("SELECT symbol, enabled, notes, created_at FROM symbol_universe ORDER BY symbol")
            list_universe_rows = cursor.fetchall()
            logger.info(f"[SNAPSHOT DIAG]   Results: {list_universe_rows}")
            logger.info("[SNAPSHOT DIAG] Then filters: [row['symbol'] for row in symbols if row.get('enabled')]")
            logger.info("[SNAPSHOT DIAG]   Note: row.get('enabled') checks if enabled is truthy (1, True, etc.)")
            
            # 4. Check for other universe tables
            logger.info("=" * 80)
            logger.info("[SNAPSHOT DIAG] TASK 4: Check for other universe-related tables")
            logger.info("=" * 80)
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' 
                AND (name LIKE '%universe%' OR name LIKE '%symbol%')
                ORDER BY name
            """)
            universe_tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"[SNAPSHOT DIAG] Tables with 'universe' or 'symbol' in name: {universe_tables}")
            for table_name in universe_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                table_count = cursor.fetchone()[0]
                logger.info(f"[SNAPSHOT DIAG]   Table '{table_name}': {table_count} rows")
            
            # 5. Check which table UI writes to (check dashboard code)
            logger.info("=" * 80)
            logger.info("[SNAPSHOT DIAG] TASK 5: Confirm which table Symbol Universe Manager UI writes to")
            logger.info("=" * 80)
            logger.info("[SNAPSHOT DIAG] UI functions used:")
            logger.info("[SNAPSHOT DIAG]   - add_universe_symbol() -> writes to symbol_universe")
            logger.info("[SNAPSHOT DIAG]   - toggle_universe_symbol() -> updates symbol_universe.enabled")
            logger.info("[SNAPSHOT DIAG]   - list_universe_symbols() -> reads from symbol_universe")
            logger.info("[SNAPSHOT DIAG] Confirmed: Symbol Universe Manager UI writes to 'symbol_universe' table")
            
            # Show all tables for reference
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            all_tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"[SNAPSHOT DIAG] All tables in database: {all_tables}")
            
            logger.info("=" * 80)
        finally:
            conn.close()
    
    # Get enabled symbols via function
    logger.info("=" * 80)
    logger.info("[SNAPSHOT DIAG] Calling get_enabled_symbols() function...")
    logger.info("=" * 80)
    
    # Trace through the function logic
    from app.core.persistence import list_universe_symbols
    all_universe_symbols = list_universe_symbols()
    logger.info(f"[SNAPSHOT DIAG] list_universe_symbols() returned {len(all_universe_symbols)} rows")
    for idx, row in enumerate(all_universe_symbols):
        logger.info(f"[SNAPSHOT DIAG]   Row {idx}: {row}")
        logger.info(f"[SNAPSHOT DIAG]     - row.get('enabled'): {row.get('enabled')} (type: {type(row.get('enabled')).__name__}, truthy: {bool(row.get('enabled'))})")
    
    symbols = get_enabled_symbols()
    # DEV: if universe is empty, use default_universe.txt for snapshot building only (no DB overwrite)
    if not symbols and os.getenv("CHAKRAOPS_DEV", "").lower() in ("1", "true", "yes"):
        try:
            from app.core.dev_seed import load_default_universe
            symbols = load_default_universe()
            logger.info("[SNAPSHOT] DEV: enabled universe empty, using default_universe.txt (%d symbols)", len(symbols))
        except Exception as e:
            logger.warning("[SNAPSHOT] DEV: failed to load default_universe: %s", e)

    # Benchmarks (SPY, QQQ) always included for regime computation; add if missing
    _BENCHMARKS = ("SPY", "QQQ")
    _seen = {normalize_symbol(s) for s in symbols}
    for b in _BENCHMARKS:
        _nb = normalize_symbol(b)
        if _nb and _nb not in _seen:
            symbols = list(symbols) + [b]
            _seen.add(_nb)
    logger.info("Benchmarks ensured: SPY, QQQ")

    # DIAGNOSTIC: Print enabled symbols from get_enabled_symbols() function
    logger.info("=" * 80)
    logger.info("[SNAPSHOT DIAG] get_enabled_symbols() final result:")
    logger.info("=" * 80)
    logger.info(f"[SNAPSHOT DIAG] Enabled symbols from get_enabled_symbols(): {symbols}")
    logger.info(f"[SNAPSHOT DIAG] Enabled symbols count: {len(symbols)}")
    logger.info(f"[SNAPSHOT DIAG] Enabled symbols (raw string values): {[repr(s) for s in symbols]}")
    logger.info(f"[SNAPSHOT DIAG] Enabled symbols (types): {[type(s).__name__ for s in symbols]}")
    
    # Show which rows passed the filter
    filtered_rows = [row for row in all_universe_symbols if row.get("enabled")]
    logger.info(f"[SNAPSHOT DIAG] Rows that passed 'if row.get(\"enabled\")' filter: {len(filtered_rows)}")
    for row in filtered_rows:
        logger.info(f"[SNAPSHOT DIAG]   Passed: symbol={repr(row['symbol'])}, enabled={row.get('enabled')}")
    
    if not symbols:
        raise ValueError("No enabled symbols in universe")
    
    # Get current time in ET
    if _ET_TZ:
        snapshot_time_et = datetime.now(_ET_TZ)
    else:
        snapshot_time_et = datetime.now(timezone.utc)
    
    snapshot_id = str(uuid4())
    snapshot_timestamp_et = snapshot_time_et.isoformat()
    
    # Determine data source based on mode
    symbol_data_map: Dict[str, Optional[pd.DataFrame]] = {}
    source = None
    
    if mode == "CSV" or mode == "AUTO":
        # Try CSV first - check multiple possible locations
        repo_root = Path(__file__).parent.parent.parent
        possible_paths = [
            repo_root / "app" / "data" / "snapshots" / "market_snapshot.csv",
            repo_root / "data" / "snapshots" / "market_snapshot.csv",
        ]
        
        csv_path = None
        for path in possible_paths:
            if path.exists():
                csv_path = path
                logger.info(f"[SNAPSHOT] CSV file found at: {path.absolute()}")
                break
        
        if csv_path is None:
            logger.warning(f"[SNAPSHOT] CSV file not found. Checked paths:")
            for path in possible_paths:
                logger.warning(f"  - {path.absolute()}")
            if mode == "CSV":
                raise ValueError(
                    f"CSV file not found. Expected at: {possible_paths[0].absolute()} "
                    f"or {possible_paths[1].absolute()}"
                )
        else:
            try:
                symbol_data_map = _load_snapshot_from_csv(csv_path)
                csv_symbol_count = len([s for s in symbol_data_map.values() if s is not None])
                
                # DIAGNOSTIC: Print CSV symbols
                csv_symbol_keys = list(symbol_data_map.keys())
                logger.info(f"[SNAPSHOT DIAG] CSV symbol keys (raw): {csv_symbol_keys}")
                logger.info(f"[SNAPSHOT DIAG] CSV symbol keys (repr): {[repr(s) for s in csv_symbol_keys]}")
                logger.info(f"[SNAPSHOT DIAG] CSV symbol keys (upper): {[s.upper() if isinstance(s, str) else s for s in csv_symbol_keys]}")
                logger.info(f"[SNAPSHOT] Loaded {csv_symbol_count} symbols from CSV")
                
                # Defensive check: CSV must have at least 1 symbol
                if csv_symbol_count == 0:
                    raise ValueError("CSV file is empty or contains no valid symbol data")
                
                source = "CSV"
                logger.info(f"[SNAPSHOT] Using CSV source: {csv_path.absolute()}")
            except Exception as e:
                logger.error(f"[SNAPSHOT] Failed to load CSV: {e}", exc_info=True)
                if mode == "CSV":
                    raise ValueError(f"Failed to load CSV snapshot: {e}")
                # Fall through to CACHE if AUTO mode
    
    if not source and (mode == "CACHE" or mode == "AUTO"):
        # Try CACHE
        try:
            cached_data = _load_snapshot_from_cache()
            if cached_data:
                symbol_data_map = cached_data
                source = "CACHE"
                logger.info("[SNAPSHOT] Using CACHE source (last snapshot)")
        except Exception as e:
            logger.warning(f"[SNAPSHOT] Failed to load from cache: {e}")
            if mode == "CACHE":
                raise ValueError(f"Failed to load from cache: {e}")
    
    # If still no source, raise error
    if not source:
        raise ValueError(
            "No snapshot source available. Provide CSV at data/snapshots/market_snapshot.csv "
            "or ensure a previous snapshot exists in the database."
        )
    
    # Normalize all symbols for intersection calculation
    enabled_set_normalized = {normalize_symbol(s) for s in symbols}
    csv_set_normalized = {normalize_symbol(s) for s in symbol_data_map.keys()}
    
    # DIAGNOSTIC: Show intersection and difference (using normalized symbols)
    intersection = enabled_set_normalized & csv_set_normalized
    enabled_not_in_csv = enabled_set_normalized - csv_set_normalized
    csv_not_in_enabled = csv_set_normalized - enabled_set_normalized
    
    logger.info(f"[SNAPSHOT] Coverage calculation (normalized symbols):")
    logger.info(f"[SNAPSHOT]   Enabled universe symbols: {len(enabled_set_normalized)}")
    logger.info(f"[SNAPSHOT]   Snapshot symbols: {len(csv_set_normalized)}")
    logger.info(f"[SNAPSHOT]   Intersection (covered): {len(intersection)}")
    logger.info(f"[SNAPSHOT]   First 5 enabled: {sorted(list(enabled_set_normalized))[:5]}")
    logger.info(f"[SNAPSHOT]   First 5 snapshot: {sorted(list(csv_set_normalized))[:5]}")
    logger.info(f"[SNAPSHOT]   First 5 intersection: {sorted(list(intersection))[:5]}")
    logger.info(f"[SNAPSHOT DIAG] Intersection (enabled AND in CSV): {sorted(intersection)}")
    logger.info(f"[SNAPSHOT DIAG] Enabled symbols NOT in CSV: {sorted(enabled_not_in_csv)}")
    logger.info(f"[SNAPSHOT DIAG] CSV symbols NOT in enabled universe: {sorted(csv_not_in_enabled)}")
    
    # Auto-upsert CSV symbols into universe if intersection is empty
    if len(intersection) == 0 and source == "CSV":
        logger.info("=" * 80)
        logger.info("[SNAPSHOT] Intersection is empty - auto-upserting CSV symbols into symbol_universe")
        logger.info("=" * 80)
        
        from app.core.persistence import get_db_path
        import sqlite3
        
        db_path = get_db_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        try:
            # Ensure table exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbol_universe (
                    symbol TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            
            force_enabled_count = 0
            created_at = datetime.now(timezone.utc).isoformat()
            
            # Upsert each CSV symbol (normalize: UPPER(TRIM))
            for csv_symbol in csv_set_normalized:
                # Normalize: UPPER(TRIM(symbol))
                normalized_symbol = normalize_symbol(csv_symbol)
                if not normalized_symbol:
                    continue
                
                # Check if symbol already exists
                cursor.execute("SELECT symbol, enabled FROM symbol_universe WHERE symbol = ?", (normalized_symbol,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing: set enabled = 1
                    cursor.execute("""
                        UPDATE symbol_universe 
                        SET enabled = 1 
                        WHERE symbol = ?
                    """, (normalized_symbol,))
                    logger.debug(f"[SNAPSHOT] Updated existing symbol {normalized_symbol} to enabled=1")
                else:
                    # Insert new symbol
                    cursor.execute("""
                        INSERT INTO symbol_universe (symbol, enabled, notes, created_at)
                        VALUES (?, 1, ?, ?)
                    """, (normalized_symbol, f"Auto-added from CSV snapshot", created_at))
                    logger.debug(f"[SNAPSHOT] Inserted new symbol {normalized_symbol} with enabled=1")
                
                force_enabled_count += 1
            
            conn.commit()
            logger.info(f"[SNAPSHOT] Force-enabled {force_enabled_count} symbols from CSV into symbol_universe")
            
            # Re-fetch enabled symbols after upsert
            symbols = get_enabled_symbols()
            logger.info(f"[SNAPSHOT] After upsert, enabled symbols count: {len(symbols)}")
            logger.info(f"[SNAPSHOT] Enabled symbols after upsert: {symbols}")
            
            # Normalize symbol_data_map keys to match normalized universe symbols
            # (symbol_data_map already has normalized keys from CSV loading, but ensure consistency)
            normalized_data_map: Dict[str, Optional[pd.DataFrame]] = {}
            for csv_key, df in symbol_data_map.items():
                normalized_key = normalize_symbol(csv_key)
                if normalized_key:
                    normalized_data_map[normalized_key] = df
            symbol_data_map = normalized_data_map
            logger.info(f"[SNAPSHOT] Normalized symbol_data_map keys to match universe symbols")
            
            # Recalculate intersection after normalization
            enabled_set_normalized = {normalize_symbol(s) for s in symbols}
            csv_set_normalized = {normalize_symbol(s) for s in symbol_data_map.keys()}
            intersection = enabled_set_normalized & csv_set_normalized
            logger.info(f"[SNAPSHOT] After upsert and normalization, intersection: {len(intersection)} symbols")
            
        finally:
            conn.close()
    
    # Ensure all enabled symbols are in the map (using normalized symbols)
    # Filter symbol_data_map to only include enabled symbols
    filtered_data_map: Dict[str, Optional[pd.DataFrame]] = {}
    for symbol in symbols:
        normalized_sym = normalize_symbol(symbol)
        if normalized_sym in symbol_data_map:
            filtered_data_map[normalized_sym] = symbol_data_map[normalized_sym]
        else:
            filtered_data_map[normalized_sym] = None
            logger.debug(f"[SNAPSHOT DIAG] No match for enabled symbol: {symbol} (normalized: {normalized_sym})")
    
    symbol_data_map = filtered_data_map
    
    # Count symbols with/without data
    symbols_with_data = sum(1 for v in symbol_data_map.values() if v is not None and not v.empty)
    symbols_without_data = len(symbols) - symbols_with_data
    
    logger.info(
        f"[SNAPSHOT] After filtering to enabled symbols: "
        f"{symbols_with_data} with data, {symbols_without_data} without data, "
        f"total enabled={len(symbols)}"
    )
    
    # Calculate data age (use most recent data timestamp from all symbols)
    data_age_minutes = 0.0
    if symbols_with_data > 0:
        newest_timestamp = None
        for symbol, df in symbol_data_map.items():
            if df is not None and not df.empty:
                # Get last row timestamp (most recent data point)
                if 'date' in df.columns:
                    last_date = df['date'].iloc[-1] if len(df) > 0 else None
                    if last_date is not None:
                        try:
                            dt_et = parse_snapshot_timestamp(last_date)
                            if dt_et and (newest_timestamp is None or dt_et > newest_timestamp):
                                newest_timestamp = dt_et
                        except Exception:
                            pass
        
        if newest_timestamp:
            age_delta = snapshot_time_et - newest_timestamp
            data_age_minutes = age_delta.total_seconds() / 60.0
    
    # Defensive check: If CSV loaded ≥1 symbol, snapshot MUST be persisted
    if source == "CSV" and symbols_with_data == 0:
        raise ValueError(f"CSV loaded but no symbols with data found. Expected at least 1 symbol.")
    
    # Step 2: Persist snapshot metadata (atomic write)
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        
        # Snapshot rebuild hygiene: clear stale rows before inserting
        _dev_mode = os.getenv("CHAKRAOPS_DEV", "").lower() in ("1", "true", "yes")
        if _dev_mode:
            cursor.execute("DELETE FROM market_snapshot_data")
            cursor.execute("DELETE FROM market_snapshots")
            logger.info("[SNAPSHOT] DEV mode: truncated snapshot tables before rebuild")
        else:
            cursor.execute(
                "DELETE FROM market_snapshot_data WHERE snapshot_id IN (SELECT snapshot_id FROM market_snapshots WHERE snapshot_timestamp_et = ?)",
                (snapshot_timestamp_et,),
            )
            cursor.execute("DELETE FROM market_snapshots WHERE snapshot_timestamp_et = ?", (snapshot_timestamp_et,))
        
        # Mark previous snapshots as not frozen (only one active snapshot)
        cursor.execute("""
            UPDATE market_snapshots
            SET is_frozen = 0
            WHERE is_frozen = 1
        """)
        previous_frozen_count = cursor.rowcount
        if previous_frozen_count > 0:
            logger.debug(f"[SNAPSHOT] Marked {previous_frozen_count} previous snapshot(s) as not frozen")
        
        # Insert snapshot metadata (include source in provider field)
        provider_value = f"snapshot-{source.lower()}"
        cursor.execute("""
            INSERT INTO market_snapshots (
                snapshot_id, snapshot_timestamp_et, provider,
                symbol_count, data_age_minutes, is_frozen, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_id,
            snapshot_timestamp_et,
            provider_value,
            len(symbols),
            data_age_minutes,
            1,  # is_frozen = True
            created_at,
        ))
        
        # Verify exactly one row was inserted
        if cursor.rowcount != 1:
            raise RuntimeError(f"Failed to insert snapshot metadata. Expected 1 row, got {cursor.rowcount}")
        
        logger.debug(f"[SNAPSHOT] Inserted snapshot metadata: id={snapshot_id}, is_frozen=1")
        
        # Insert snapshot data (one row per symbol) - use normalized symbols
        inserted_rows = 0
        for symbol in symbols:
            normalized_sym = normalize_symbol(symbol)
            df = symbol_data_map.get(normalized_sym)
            has_data = 1 if df is not None and not df.empty else 0
            data_json = None
            
            if has_data:
                # Step 1: Convert DataFrame to JSON (Fix JSON serialization)
                try:
                    # Convert to dict with date as string
                    df_dict = df.to_dict(orient='records')
                    
                    # Step 1: Safe JSON serializer for pandas Timestamp/datetime objects
                    def json_serializer(obj):
                        """Convert pandas Timestamp/datetime to ISO string for JSON serialization."""
                        # Handle pandas Timestamp
                        if hasattr(obj, 'to_pydatetime'):
                            try:
                                return obj.to_pydatetime().isoformat()
                            except Exception:
                                pass
                        # Handle datetime objects (including timezone-aware)
                        if hasattr(obj, 'isoformat'):
                            try:
                                return obj.isoformat()
                            except Exception:
                                pass
                        # Handle date objects
                        if hasattr(obj, 'isoformat') and hasattr(obj, 'year'):
                            try:
                                return obj.isoformat()
                            except Exception:
                                pass
                        # Handle numpy types (if available)
                        try:
                            import numpy as np
                            if isinstance(obj, (np.integer, np.floating)):
                                return float(obj)
                            if isinstance(obj, np.ndarray):
                                return obj.tolist()
                        except ImportError:
                            pass
                        # Fallback: convert to string
                        return str(obj)
                    
                    data_json = json.dumps(df_dict, default=json_serializer)
                except Exception as e:
                    logger.error(
                        f"[SNAPSHOT] Failed to serialize {normalized_sym} data: {e}. "
                        f"Symbol will be stored with has_data=0.",
                        exc_info=True
                    )
                    has_data = 0
                    data_json = None
            
            # Store with normalized symbol
            cursor.execute("""
                INSERT INTO market_snapshot_data (
                    snapshot_id, symbol, data_json, has_data, created_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (snapshot_id, normalized_sym, data_json, has_data, created_at))
            inserted_rows += 1
        
        # Verify all symbols were inserted
        if inserted_rows != len(symbols):
            raise RuntimeError(
                f"Failed to insert all symbol data. Expected {len(symbols)} rows, got {inserted_rows}"
            )
        
        # Step 2: Atomic commit - all or nothing
        conn.commit()
        
        # Step 2: Log successful snapshot build with row counts
        logger.info(
            f"[SNAPSHOT] inserted snapshot_id={snapshot_id} rows={inserted_rows} symbols "
            f"(with_data={symbols_with_data}, without_data={symbols_without_data})"
        )
        
        logger.info(
            f"[SNAPSHOT] Built snapshot {snapshot_id[:8]}... using {source}, "
            f"symbols={symbols_with_data}/{len(symbols)}"
        )
        
        return {
            "snapshot_id": snapshot_id,
            "snapshot_timestamp_et": snapshot_timestamp_et,
            "provider": provider_value,
            "symbol_count": len(symbols),
            "data_age_minutes": data_age_minutes,
            "is_frozen": True,
            "source": source,
            "symbols_with_data": symbols_with_data,
            "symbols_without_data": symbols_without_data,
        }
    
    except Exception as e:
        # Step 2: Rollback on error and re-raise with clear message
        if 'conn' in locals():
            conn.rollback()
        logger.error(f"[SNAPSHOT] Failed to build snapshot: {e}", exc_info=True)
        raise RuntimeError(f"Snapshot build failed: {e}") from e
    finally:
        if 'conn' in locals():
            conn.close()


def get_active_snapshot() -> Optional[Dict[str, Any]]:
    """Get the most recent active snapshot.
    
    Returns
    -------
    Optional[Dict[str, Any]]
        Snapshot metadata, or None if no snapshot exists.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return None
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT snapshot_id, snapshot_timestamp_et, provider,
                   symbol_count, data_age_minutes, is_frozen, created_at
            FROM market_snapshots
            WHERE is_frozen = 1
            ORDER BY snapshot_timestamp_et DESC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        if row:
            return {
                "snapshot_id": row[0],
                "snapshot_timestamp_et": row[1],
                "provider": row[2],
                "symbol_count": row[3],
                "data_age_minutes": row[4],
                "is_frozen": bool(row[5]),
                "created_at": row[6],
            }
        
        return None
    finally:
        conn.close()


def load_snapshot_data(snapshot_id: str) -> Dict[str, Any]:
    """Load snapshot data (symbol -> DataFrame mapping).
    
    Parameters
    ----------
    snapshot_id:
        Snapshot ID to load.
    
    Returns
    -------
    Dict[str, Any]
        Dictionary mapping symbol to DataFrame (or None if missing data).
    """
    import json
    import pandas as pd
    
    db_path = get_db_path()
    if not db_path.exists():
        return {}
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT symbol, data_json, has_data
            FROM market_snapshot_data
            WHERE snapshot_id = ?
            ORDER BY symbol
        """, (snapshot_id,))
        
        symbol_to_df: Dict[str, Any] = {}
        
        for row in cursor.fetchall():
            symbol_raw = row[0]
            data_json = row[1]
            has_data = bool(row[2])
            
            # Normalize symbol from DB
            symbol = normalize_symbol(symbol_raw)
            
            if has_data and data_json:
                try:
                    # Parse JSON back to DataFrame
                    records = json.loads(data_json)
                    df = pd.DataFrame(records)
                    # Ensure date column is datetime
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                    symbol_to_df[symbol] = df
                except Exception as e:
                    logger.warning(f"[SNAPSHOT] Failed to parse data for {symbol}: {e}")
                    symbol_to_df[symbol] = None
            else:
                symbol_to_df[symbol] = None
        
        return symbol_to_df
    
    finally:
        conn.close()


def get_latest_snapshot_id() -> Optional[str]:
    """Get the latest active snapshot ID.
    
    Returns
    -------
    Optional[str]
        Latest snapshot ID, or None if no snapshot exists.
    """
    snapshot = get_active_snapshot()
    if snapshot:
        return snapshot["snapshot_id"]
    return None


def get_previous_snapshot_id(latest_id: str) -> Optional[str]:
    """Get the previous snapshot ID (before latest).
    
    Parameters
    ----------
    latest_id:
        Latest snapshot ID to exclude.
    
    Returns
    -------
    Optional[str]
        Previous snapshot ID, or None if no previous snapshot exists.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return None
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT snapshot_id
            FROM market_snapshots
            WHERE snapshot_id != ?
            ORDER BY snapshot_timestamp_et DESC
            LIMIT 1
        """, (latest_id,))
        
        row = cursor.fetchone()
        if row:
            return row[0]
        return None
    finally:
        conn.close()


def get_snapshot_prices(snapshot_id: str) -> Dict[str, Dict[str, Optional[float]]]:
    """Get symbol -> price/volume/iv_rank mapping from snapshot (normalized symbols, Phase 2B Step 3).
    
    Parameters
    ----------
    snapshot_id:
        Snapshot ID to load data from.
    
    Returns
    -------
    Dict[str, Dict[str, Optional[float]]]
        Dictionary mapping normalized symbol to dict with:
        - price: float | None
        - volume: float | None
        - iv_rank: float | None
        Returns empty dict if snapshot not found or no data.
    """
    import pandas as pd
    
    symbol_to_df = load_snapshot_data(snapshot_id)
    symbol_data: Dict[str, Dict[str, Optional[float]]] = {}
    
    for symbol, df in symbol_to_df.items():
        if df is not None and not df.empty:
            data: Dict[str, Optional[float]] = {
                "price": None,
                "volume": None,
                "iv_rank": None,
            }
            
            # Get latest close price (last row)
            if 'close' in df.columns:
                latest_close = df['close'].iloc[-1]
                if pd.notna(latest_close):
                    data["price"] = float(latest_close)
            elif 'price' in df.columns:
                # Fallback to 'price' column if 'close' not available
                latest_price = df['price'].iloc[-1]
                if pd.notna(latest_price):
                    data["price"] = float(latest_price)
            
            # Get volume (if available)
            if 'volume' in df.columns:
                latest_volume = df['volume'].iloc[-1]
                if pd.notna(latest_volume):
                    data["volume"] = float(latest_volume)
            
            # Get IV rank (if available)
            if 'iv_rank' in df.columns:
                latest_iv_rank = df['iv_rank'].iloc[-1]
                if pd.notna(latest_iv_rank):
                    data["iv_rank"] = float(latest_iv_rank)
            elif 'iv' in df.columns:
                # Fallback: try 'iv' column (will be None if not found)
                latest_iv = df['iv'].iloc[-1]
                if pd.notna(latest_iv):
                    # If IV is provided but not IV rank, we can't compute IV rank
                    # Leave it as None
                    pass
            if data.get("iv_rank") is None:
                logger.debug("[SNAPSHOT] %s: no iv_rank; iv_too_low gate skipped (iv_rank treated as None)", symbol)
            
            symbol_data[symbol] = data
    
    return symbol_data


__all__ = [
    "build_market_snapshot",
    "get_active_snapshot",
    "load_snapshot_data",
    "init_snapshot_schema",
    "parse_snapshot_timestamp",
    "ensure_et_aware",
    "normalize_symbol",
    "get_latest_snapshot_id",
    "get_previous_snapshot_id",
    "get_snapshot_prices",
]
