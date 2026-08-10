# Operator Runbook — ChakraOps (canonical pointer)

**Canonical daily operator procedures live here:**

→ [`chakraops/docs/RUNBOOK_OPERATOR_DAILY.md`](../../chakraops/docs/RUNBOOK_OPERATOR_DAILY.md)

## Quick reference

| Item | Value |
|------|--------|
| Start | `.\scripts\start_chakraops.ps1` |
| UI | http://127.0.0.1:18873/ |
| API health | http://127.0.0.1:18800/api/healthz |
| Stop | `.\scripts\stop_chakraops.ps1` |

## Broker (read-only)

When token configured → expect `ROBINHOOD_MCP_READ_ONLY_AVAILABLE`.  
When not → `UNAUTHENTICATED` / `ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER`; continue with manual portfolio. Never enable broker writes.

## Related

- Startup/shutdown: `chakraops/docs/RUNBOOK_STARTUP_SHUTDOWN.md`
- Production deploy/ops: [PRODUCTION_RUNBOOK.md](./PRODUCTION_RUNBOOK.md)
- Backup: `chakraops/docs/RUNBOOK_BACKUP_RESTORE.md`
