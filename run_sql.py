#!/usr/bin/env python3
"""Run SQL queries from .sql file."""

import sqlite3
from app.core.config.paths import DB_PATH

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

queries = [
    ("market_regimes", "SELECT COUNT(*) FROM market_regimes"),
    ("csp_evaluations", "SELECT COUNT(*) FROM csp_evaluations"),
    ("alerts", "SELECT COUNT(*) FROM alerts"),
    ("regime_snapshots", "SELECT COUNT(*) FROM regime_snapshots"),
    ("open_positions", "SELECT COUNT(*) FROM positions WHERE status='OPEN'"),
    ("closed_positions", "SELECT COUNT(*) FROM positions WHERE status='CLOSED'"),
    ("position_history (trades)", "SELECT COUNT(*) FROM trades"),
]

print("=" * 60)
print("Database Table Counts")
print("=" * 60)

for name, query in queries:
    try:
        cursor.execute(query)
        count = cursor.fetchone()[0]
        print(f"{name:30} {count:>10}")
    except sqlite3.OperationalError as e:
        print(f"{name:30} {'ERROR: ' + str(e):>10}")

print("=" * 60)

conn.close()
