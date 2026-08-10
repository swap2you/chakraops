# R41 — Whole-Application Screen Contract

Machine-readable companions:
- `SCREEN_INVENTORY.json`
- `CONTROL_INVENTORY.csv`
- `DATA_LINEAGE.csv`

## Acceptance IDs

| ID | Requirement | Status |
|----|-------------|--------|
| R41-A1 | Inventory every React route, nav link, redirect, conditional/orphan | PASS |
| R41-A2 | Inventory page sections/cards/tables/controls via data-testid scan | PASS (regenerate script) |
| R41-A3 | Control matrix with classification | PASS (`CONTROL_INVENTORY.csv`) |
| R41-A4 | Material field lineage | PASS (`DATA_LINEAGE.csv`) |
| R41-A5 | LIVE mock/placeholder financial values located/labeled | PASS — MOCK artifact forensics-only; Paper/Backtest SIMULATION; mock scenarios unmounted |
| R41-A6 | Permanent Playwright E2E/screenshot harness | PASS (`frontend/e2e`, `playwright.config.ts`) |
| R41-A7 | Canonical artifacts | PASS (this folder) |
| R41-A8 | R40.1 regression-proof | PASS (`tests/test_r41_r401_regressions.py` + ops smoke) |

## Canonical routes (19)

See `SCREEN_INVENTORY.json`. Source of truth: `frontend/src/app/App.tsx`.

## Orphans

- `CommandPalette` / `CommandBar` — unmounted (R49 consolidation)
- `pages/_quarantine/*` — not routed

## Browser harness

```
cd frontend
npx playwright test
```

Requires backend `18800` and frontend `18873`. Screenshots → `out/verification/R41/screenshots/`.

Safety: no broker writes; mutations require `CHAKRAOPS_E2E_ALLOW_MUTATIONS=1`.

## Regenerate inventories

```
python scripts/generate_r41_screen_contract.py
```
