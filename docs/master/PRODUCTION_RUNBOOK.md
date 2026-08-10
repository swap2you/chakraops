# Production Runbook — ChakraOps

**Audience:** Single-operator production / production-mode local.  
**Safety:** `manual_only` · `trade_execution=false` · no broker writes · scheduler fail-closed off.

## Ports (fixed)

| Service | Port |
|---------|------|
| Backend | **18800** |
| Frontend | **18873** |

Do not use 8000/5173 for ChakraOps.

## Start / health

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\start_chakraops.ps1
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/healthz" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:18873/" -UseBasicParsing
```

## Environment (secrets never committed)

| Variable | Role |
|----------|------|
| `ORATS_API_TOKEN` | Options/market data |
| `DATABASE_URL` | Optional; `postgresql+psycopg://...` for Postgres; unset → local SQLite under `data/` |
| `ROBINHOOD_MCP_ACCESS_TOKEN` / `ROBINHOOD_MCP_TOKEN_PATH` | Read-only broker (R52) |
| `CHAKRAOPS_SCHEDULER_ENABLED` | Must remain `false` unless explicit operator opt-in |
| Slack webhooks | Optional notifications |

See `chakraops/.env.example`.

## Data

- **Transactional:** SQLAlchemy data platform (`app/core/data_platform/`); prefer Postgres in production.
- **Research:** Parquet + DuckDB — not multi-process transactional writes ([RESEARCH_DATA.md](./RESEARCH_DATA.md)).
- **Backup:** `chakraops/docs/RUNBOOK_BACKUP_RESTORE.md` — exclude `.env` / credentials.
- Inventory legacy stores before cutover: `python -m app.core.data_platform.migrate_sqlite_inventory` (from `chakraops/`).

## Broker production auth

Cursor MCP auth ≠ production server auth. Token must live in protected secrets/volume. Missing token → app remains up (`UNAUTHENTICATED`); do not invent balances.

## Deploy notes (R57 foreshadow)

Domain/VPS binding may be marked `DOMAIN_VPS_BINDING_EXTERNAL` until supplied. Finish stack + local production-mode acceptance first. No auto trading in any environment.

## Shutdown

```powershell
.\scripts\stop_chakraops.ps1
```

## Operator daily path

[OPERATOR_RUNBOOK.md](./OPERATOR_RUNBOOK.md)
