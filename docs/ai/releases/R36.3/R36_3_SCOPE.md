# R36.3 — Whole-Application Trust & Wiring Stabilization

## Scope
Audit and fix end-to-end wiring/trust before strategy complexity. No threshold tuning.

## Baseline
- SHA at start of implementation: `d21143f` (governance mainline mode)
- Ports: backend 18800, frontend 18873
- Safety: `manual_only=true`, `trade_execution=false`, scheduler `master_enabled=false`

## Delivered
- Route inventory: `docs/ai/validation/R36_3_ROUTE_INVENTORY.json`
- Findings register: `docs/ai/validation/R36_3_FINDINGS.json` (0 open BLOCKER/HIGH)
- Dashboard: canonical recommendations primary; legacy tiers/shares demoted
- Trade Ticket in Sidebar
- Portfolio buying power from stored account summary
- Universe V2 primary; legacy eval under details
- Symbol Diagnostics: suppress diagnostic next-action when canonical OK
- `source.ts` fail-closed (no default MOCK)
- Command palette/bar path rewrite
- System: deferred earnings probe + store integrity loads

## Explicitly deferred (MEDIUM, non-blocking)
- Orphan page module deletion → R39
- Today localStorage queue → R39 Command Center

## Universe V2 market validation
- Freshness endpoint returned `stale=true`, age ~29 days (snapshot from 2026-07-12)
- Documented as blocked on provider freshness for market-hours revalidation; fail-closed behavior preserved (no forced recommendations from stale data)
- Action-needed: `decision_source=canonical_decision_engine`, `manual_only=true`, actionable count 0 (Stay in Cash / empty valid)
