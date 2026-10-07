#!/usr/bin/env python3
"""Run SQL queries from .sql file."""

import sqlite3
from app.core.config.paths import DB_PATH

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# Read queries from .sql file
queries = [
    ("market_regimes", "SELECT * FROM market_regimes ORDER BY created_at DESC"),
    ("csp_evaluations", "SELECT * FROM csp_evaluations ORDER BY created_at DESC"),
    ("alerts", "SELECT * FROM alerts ORDER BY created_at DESC"),
    ("regime_snapshots", "SELECT * FROM regime_snapshots ORDER BY created_at DESC"),
    ("open_positions", "SELECT * FROM positions WHERE status='OPEN' ORDER BY entry_date DESC"),
    ("closed_positions", "SELECT * FROM positions WHERE status='CLOSED' ORDER BY entry_date DESC"),
    ("position_history (trades)", "SELECT * FROM trades ORDER BY created_at DESC"),
]

print("=" * 80)
print("Database Query Results")
print("=" * 80)

for name, query in queries:
    print(f"\n{name}:")
    print("-" * 80)
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            print("  (no rows)")
        else:
            # Get column names
            column_names = [description[0] for description in cursor.description]
            print(f"  Columns: {', '.join(column_names)}")
            print(f"  Rows: {len(rows)}")
            
            # Show first 5 rows
            for i, row in enumerate(rows[:5], 1):
                print(f"  Row {i}: {row}")
            if len(rows) > 5:
                print(f"  ... and {len(rows) - 5} more rows")
    except sqlite3.OperationalError as e:
        print(f"  ERROR: {e}")

print("\n" + "=" * 80)

conn.close()
