# R70 Final Closure — Batch A Closure

**Status:** CLOSED (technically complete for Batch A scope)  
**Date:** 2026-08-12  
**Findings:** COMPLETE-002, COMPLETE-003, COMPLETE-008, COMPLETE-009, COMPLETE-018/020 (display), CODEX FINAL-002

## Root causes fixed

1. **Capital authority** — Guardrails/sizing read manual recovery `$0` while fresh broker cash existed. New `capital_authority_r70` prefers fresh broker cash; buying_power stays distinct; CSP uses cash not margin BP; Roth not pooled; age threshold blocks stale sizing.
2. **Account registry empty** — Broker aliases were a separate path. `account_bridge_r70` idempotently bridges aliases into `accounts.json`, establishes default `acct_individual`, marks agentic non-execution.
3. **Reconcile OK on disjoint books** — `/positions/unified/reconcile-diff` now attaches `broker_vs_manual`; overall status becomes Review when broker/manual diverge.
4. **Historicalize unsafe** — Defaults `dry_run=True`; orphans vs fresh broker only; refuse stale/missing; require `confirm=true` for mutation.
5. **CC eligibility** — `get_holdings_for_evaluation` uses fresh broker shares when available.
6. **Portfolio stubs** — Accounts / Orders / Reconciliation / Risk DATA_BLOCKED wired to real data.

## Tests

```
.\.venv\Scripts\python.exe -m pytest tests/test_r70_final_closure_batch_a.py tests/test_r70_abcd_batch_a_lenses.py -q --tb=short
# 13 passed

.\.venv\Scripts\python.exe -m pytest tests/test_r259_guardrails.py tests/test_r260_sizing.py tests/test_r277_portfolio_cc_eligible.py -q --tb=short
# 22 passed

npm run test -- --run src/pages/PortfolioPage.test.tsx
# 20 passed
```

## Files

- `app/core/portfolio/capital_authority_r70.py` (new)
- `app/core/accounts/account_bridge_r70.py` (new)
- `app/core/accounts/service.py`, `holdings_db.py`
- `app/core/portfolio/guardrails_r259.py`, `live_position_lenses_r70.py`
- `app/api/ui_routes.py`
- `frontend/src/pages/PortfolioPage.tsx`, `api/queries.ts`, `api/types.ts`
- `tests/test_r70_final_closure_batch_a.py` (new)

## Preserved

- Robinhood READ_ONLY / write denylist / masked IDs
- manual_only / trade_execution=false
- No hardcoded UAT balances
