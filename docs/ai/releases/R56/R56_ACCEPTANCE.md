# R56 Acceptance — Strategy Workspace Separation + Navigation Consolidation

## Status

`R56_TECHNICALLY_COMPLETE` (Cursor implementation; independent review not claimed)

## Safety

HARD SAFETY unchanged: read-only broker · manual_only · no broker writes.

## Acceptance

| ID | Requirement | Result |
|----|-------------|--------|
| R56-A1 | `/opportunities` is primary strategy surface with Options / Stocks / ETF-Hedge tabs | PASS — `?strategy=options\|stocks\|etf-hedge` |
| R56-A2 | Options workspace shows CSP / CC (not duplicated as separate primary routes) | PASS |
| R56-A3 | Stocks workspace shows Shares bucket | PASS |
| R56-A4 | ETF/Hedge honest deferred / advisory empty (no fake optimizer) | PASS |
| R56-A5 | Sidebar compact IA: Command Center, Opportunities, Portfolio (+ Journal), Research, Strategy Lab (+ Learn), Operations, Advanced | PASS |
| R56-A6 | Positions removed from primary nav; `/positions` → `/portfolio?tab=holdings` preserved | PASS |
| R56-A7 | Wheel remains Advanced (admin/recovery), not Opportunities primary | PASS |
| R56-A8 | R53 Portfolio / BrokerLivePanel WIP preserved | PASS — enhanced around, not replaced |
| R56-A9 | Unit tests: Sidebar, Opportunities tabs, positions redirect | PASS |

## Screenshot / control inventory

**Deferred:** `scripts/generate_r41_screen_contract.py` still writes inventories under `docs/ai/releases/R41/` and embeds an R41 route table. Regenerating now would overwrite R41 contract artifacts without an R56-specific output path. Re-run / extend that script in a later polish pass (or R60 evidence pack) with an R56 OUT dir before claiming fresh SCREEN/CONTROL inventories for R56.

## Verify

```text
cd frontend
npx vitest run src/layout/Sidebar.test.tsx src/pages/OpportunitiesPage.test.tsx src/app/routeRedirects.test.tsx
```

Manual: open `/opportunities`, switch Options → Stocks → ETF/Hedge; confirm `/positions` lands on Portfolio holdings; confirm Sidebar has no Positions link and Wheel under Advanced.

## Out of scope

R57+ · broker writes · full ETF/Hedge optimizer · regenerating R41 screen contract into R56.
