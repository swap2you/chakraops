# A_BATCH_CLOSURE — Position Truth

## Baseline SHA
56e76be9719f603e6441fc69100e2733c8dc9dd2

## Findings closed
- F-001 BLOCKER — phantom NVDA live rows (81) no longer drive LIVE counts; orphans historicalized + rebuild
- F-006 MEDIUM — explicit lenses; Command Center LIVE from broker; Guardrails/Portfolio labeled manual/risk
- F-008 MEDIUM — integrity check never-run → NOT_RUN (not false OK)

## Root cause
Open-mirror orphans in positions_unified (`live_shares_{uuid}`) accumulated because DELETE did not un-mirror. Command Center counted unified DB as LIVE. Integrity health defaulted to OK when never executed. Broker snapshot was parallel-only.

## Paths changed
- app/core/portfolio/live_position_lenses_r70.py (new)
- app/core/portfolio/positions_unified_store_r279.py (NOT_RUN default)
- app/api/ui_routes.py (live-lenses API, historicalize, unmirror on delete, system-health block)
- frontend Dashboard/Portfolio labels + live lenses hook
- tests/test_r70_abcd_batch_a_lenses.py

## Data changes
- Backup: out/verification/R70-ABCD/A/backups/positions.db.*.bak (untracked)
- historicalize_orphan_unified_live_shares moved 81 orphan NVDA live_shares → positions_closed then rebuild → open=2 (manual AAPL/SPY)
- Forensics: out/verification/R70-ABCD/A/POSITION_STORE_FORENSICS.md

## Tests
- test_r70_abcd_batch_a_lenses.py (5)
- DashboardPage + canonical Vitest

## Runtime
- live lenses: live_open_count=3 from broker, READ_ONLY_AVAILABLE, FRESH
- integrity: NOT_RUN
- reconcile: OK (unified live shares=2 matches holdings)

## Safety
manual_only=true · trade_execution=false · broker read-only unchanged
