import csv
import sqlite3
from pathlib import Path

DB_PATH = Path("data/chakraops.db")
CSV_PATH = Path("ChakraOps_Core_Watchlist.csv")

def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH.resolve()}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Hard reset enabled flags
    cur.execute("UPDATE symbol_universe SET enabled = 0")

    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        if "symbol" not in reader.fieldnames:
            raise ValueError("CSV must contain a 'symbol' column")

        for row in reader:
            symbol = row["symbol"].strip().upper()
            notes = row.get("notes") or row.get("name") or "imported"

            if not symbol:
                continue

            cur.execute(
                """
                INSERT INTO symbol_universe (symbol, enabled, notes)
                VALUES (?, 1, ?)
                ON CONFLICT(symbol)
                DO UPDATE SET
                    enabled = 1,
                    notes = excluded.notes
                """,
                (symbol, notes),
            )

    conn.commit()
    conn.close()

    print("Universe import complete.")

if __name__ == "__main__":
    main()
