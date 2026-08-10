# R40.1 — Final Acceptance Stabilization — Scope

## Baseline
- Branch: `main`
- Start SHA: `99eb213`
- Goal: stabilize final acceptance blockers/highs without claiming independent COMPLETE.

## In scope
1. Scheduler fail-closed `_load_env` (shell wins; force master+legacy false unless allow flag)
2. Exclusive eval coordinator for all full-universe entry points (HTTP 409 when busy)
3. Wheel V2 cash honesty (never total_capital as cash; account-scoped balances)
4. ORATS live/strikes field_presence side-specific keys
5. Universe CSV unique symbols (documented count)
6. R40 backtest entitlement honesty (no fake hist-complete claim)
7. Slack CODE_READY vs CONFIGURED
8. Constraints lock note + clean `.env.example`
9. Status docs → `FINAL_ACCEPTANCE_HOLD`
10. Focused regression tests `test_r401_*`

## Out of scope
- Broker writes / auto-trading
- Committing/pushing (parent gates)
- Changing operator `.env` secret values
- Fake ORATS historical options completeness

## Acceptance target status
`FINAL_ACCEPTANCE_HOLD` pending Codex + Cowork independent confirmation.
Program honesty string when blocked on external hist: `TECHNICALLY_READY_WITH_EXTERNAL_BACKTEST_ENTITLEMENT_GAP`.
