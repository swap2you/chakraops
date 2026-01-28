# DEV Workflow — Off-Hours Usage (No Theta, No yfinance)

This document describes how to run the dashboard and snapshot/CSP flow **off-hours** with zero dependency on live Theta or yfinance.

---

## How to use in DEV off-hours

1. **Set DEV mode**  
   `CHAKRAOPS_DEV=1` (or `true` / `yes`). This enables:
   - Seed Snapshot from fixture (no network)
   - Default universe fallback when the enabled universe is empty

2. **Create or update the EOD fixture**  
   The fixture is `app/data/fixtures/eod_seed.csv` with columns: `symbol`, `price`, `volume`, `iv_rank`, `timestamp` (ET ISO).

   - **From existing snapshot:**  
     ```bash
     python tools/generate_eod_seed_fixture.py
     ```  
     This writes/overwrites `app/data/fixtures/eod_seed.csv` from `app/data/snapshots/market_snapshot.csv` if that file exists; otherwise it writes a minimal template (SPY, QQQ, AAPL, MSFT).

   - **Manually:** Create `app/data/fixtures/eod_seed.csv` with one row per symbol and the five columns above. Use a current ET timestamp in ISO format for `timestamp`.

3. **In the dashboard**  
   - Open the **Market Snapshot** section.
   - Click **“Seed Snapshot from Last Close (DEV)”**.  
     This copies the fixture to `app/data/snapshots/market_snapshot.csv` (no DB writes, no network).
   - If the fixture is missing, the UI shows an error and the steps above to generate it.
   - Click **“Build New Snapshot”**.  
     This always rebuilds from the **current** `market_snapshot.csv`, refreshes the active snapshot, and runs one heartbeat evaluation cycle so CSP candidates update immediately.

4. **CSP candidates and rejection details**  
   After a build (and the triggered evaluation), open **“Why symbols were rejected”** in the CSP Candidates section to see, per symbol: `eligible`, `score`, `rejection_reasons`, and the numeric inputs (`price`, `volume`, `iv_rank`, `regime`, `snapshot_age_minutes`). All of this comes from the evaluations already written by the heartbeat (no new DB tables).

5. **DB path**  
   When multiple `.db` files exist in the data directory, the Market Snapshot section shows which DB file is used. The canonical path is logged at startup via `[CONFIG] Using DB_PATH=...`.

---

## Summary

- **Fixture:** `app/data/fixtures/eod_seed.csv` — source for off-hours seeding.
- **Generate fixture:** `python tools/generate_eod_seed_fixture.py`.
- **Seed (DEV):** Copies fixture → `market_snapshot.csv`; no yfinance, no Theta.
- **Build:** Always uses current `market_snapshot.csv`, then runs one evaluation cycle so CSP results are up to date without restarting the heartbeat.

---

## Phase 5 next (TODO — no implementation yet)

Phase 5 next: Backtesting engine, Greeks-aware CSP logic, options chain integration.
