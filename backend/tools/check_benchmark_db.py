#!/usr/bin/env python3
"""Check benchmark symbols in database."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from app.core.config.paths import DB_PATH
from app.core.market_snapshot import get_latest_snapshot_id

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()
sid = get_latest_snapshot_id()

print("=" * 80)
print("Benchmark Symbols in Database")
print("=" * 80)
print(f"Latest snapshot_id: {sid}\n")

cursor.execute("""
    SELECT symbol, has_data, 
           CASE 
               WHEN data_json IS NULL THEN 'NULL'
               WHEN LENGTH(data_json) = 0 THEN 'EMPTY'
               ELSE 'HAS_DATA'
           END as json_status,
           LENGTH(data_json) as json_length
    FROM market_snapshot_data 
    WHERE snapshot_id = ? AND symbol IN ('SPY', 'QQQ', 'SPX')
    ORDER BY symbol
""", (sid,))

rows = cursor.fetchall()
if rows:
    print("SPY/QQQ/SPX in market_snapshot_data:")
    for row in rows:
        print(f"  {row[0]}: has_data={row[1]}, json={row[2]}, length={row[3]}")
else:
    print("  No SPY/QQQ/SPX found in market_snapshot_data")

print("\n" + "=" * 80)
print("All symbols in latest snapshot:")
print("=" * 80)
cursor.execute("""
    SELECT symbol, has_data
    FROM market_snapshot_data 
    WHERE snapshot_id = ?
    ORDER BY symbol
""", (sid,))
all_rows = cursor.fetchall()
for row in all_rows:
    print(f"  {row[0]}: has_data={row[1]}")

conn.close()
