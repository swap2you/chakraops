# Cowork Browser-Only UAT Handoff — R31–R35

**Do not run PowerShell.** Cursor executed Windows operational smoke separately.

Repository: `release/R31-R35-program`  
Backend: `http://127.0.0.1:8000`  
Frontend: `http://127.0.0.1:5173`

## Checks Cowork can execute

1. **System Diagnostics → Operations** — scheduler master disabled; jobs show disabled
2. **Operations status** — `manual_only: true`, `trade_execution: false`, `orats_token_present` boolean only (no value)
3. **No broker controls** anywhere in UI
4. **Dashboard** — canonical recommendations display
5. **Today** — canonical recommendations display
6. **Symbol Diagnostics** — fail-closed when data unavailable
7. **Manual-only wording** on trade surfaces
8. **Stay in Cash** valid outcome visible
9. **Backtest** — simulation warning present
10. **Pagination** on list pages
11. **Console** — no errors on core navigation
12. **Network tab** — no credential leakage in requests/responses

## Out of scope for Cowork

- PowerShell backup scripts
- Live smoke startup/shutdown
- Destructive retention cleanup
- Scheduler enablement

Evidence template: `out/verification/R35.0/cowork_browser_uat.md`
