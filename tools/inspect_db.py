#!/usr/bin/env python3
"""Database inspection tool for ChakraOps.

Usage:
    python tools/inspect_db.py

Prints:
    - DB_PATH absolute path
    - Row counts for key tables
    - Latest 3 rows from market_snapshots and market_regimes
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from app.core.config.paths import DB_PATH

def inspect_db():
    """Inspect ChakraOps database and print key information."""
    print("=" * 80)
    print("ChakraOps Database Inspection")
    print("=" * 80)
    print(f"\nDB_PATH: {DB_PATH.absolute()}")
    print(f"DB exists: {DB_PATH.exists()}")
    
    if not DB_PATH.exists():
        print("\n⚠️  Database file does not exist!")
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        # Table counts
        print("\n" + "=" * 80)
        print("Table Counts")
        print("=" * 80)
        
        tables = [
            "market_snapshots",
            "market_snapshot_data",
            "market_regimes",
            "csp_evaluations",
            "symbol_universe",
        ]
        
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"{table:30} {count:>10}")
            except sqlite3.OperationalError as e:
                print(f"{table:30} {'ERROR: ' + str(e):>10}")
        
        # Latest market_snapshots
        print("\n" + "=" * 80)
        print("Latest 3 market_snapshots")
        print("=" * 80)
        try:
            cursor.execute("""
                SELECT snapshot_id, snapshot_timestamp_et, provider, symbol_count, 
                       data_age_minutes, is_frozen, created_at
                FROM market_snapshots
                ORDER BY created_at DESC
                LIMIT 3
            """)
            rows = cursor.fetchall()
            if rows:
                columns = [desc[0] for desc in cursor.description]
                print(f"Columns: {', '.join(columns)}")
                for i, row in enumerate(rows, 1):
                    print(f"\nRow {i}:")
                    for col, val in zip(columns, row):
                        print(f"  {col}: {val}")
            else:
                print("  (no rows)")
        except sqlite3.OperationalError as e:
            print(f"  ERROR: {e}")
        
        # Latest market_regimes
        print("\n" + "=" * 80)
        print("Latest 3 market_regimes")
        print("=" * 80)
        try:
            cursor.execute("""
                SELECT snapshot_id, regime, benchmark_symbol, benchmark_return, 
                       computed_at, created_at
                FROM market_regimes
                ORDER BY created_at DESC
                LIMIT 3
            """)
            rows = cursor.fetchall()
            if rows:
                columns = [desc[0] for desc in cursor.description]
                print(f"Columns: {', '.join(columns)}")
                for i, row in enumerate(rows, 1):
                    print(f"\nRow {i}:")
                    for col, val in zip(columns, row):
                        print(f"  {col}: {val}")
            else:
                print("  (no rows)")
        except sqlite3.OperationalError as e:
            print(f"  ERROR: {e}")
        
        # Latest csp_evaluations
        print("\n" + "=" * 80)
        print("Latest 3 csp_evaluations")
        print("=" * 80)
        try:
            cursor.execute("""
                SELECT snapshot_id, symbol, eligible, score, created_at
                FROM csp_evaluations
                ORDER BY created_at DESC
                LIMIT 3
            """)
            rows = cursor.fetchall()
            if rows:
                columns = [desc[0] for desc in cursor.description]
                print(f"Columns: {', '.join(columns)}")
                for i, row in enumerate(rows, 1):
                    print(f"\nRow {i}:")
                    for col, val in zip(columns, row):
                        print(f"  {col}: {val}")
            else:
                print("  (no rows)")
        except sqlite3.OperationalError as e:
            print(f"  ERROR: {e}")
        
        print("\n" + "=" * 80)
        
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_db()
