# Data Model — ChakraOps (canonical)

**R51 foundation:** `chakraops/app/core/data_platform/`  
**Detail contracts:** `chakraops/docs/DATA_CONTRACT.md` (ORATS/eval semantics)

## Transactional store (SQLAlchemy)

Prefer `DATABASE_URL=postgresql+psycopg://...`. Local default: SQLite file under `chakraops/data/`.

| Table | Purpose |
|-------|---------|
| `broker_accounts` | Broker account aliases / metadata (no full account numbers in logs/evidence) |
| `broker_snapshots` | Point-in-time read-only broker snapshots (JSON payload) |
| `positions_normalized` | Canonical positions after broker/manual normalize |
| `journal_fills` | Manual fill journal rows |
| `tickets` | Manual trade tickets / queue |
| `universe_lifecycle` | Universe membership / lifecycle events |
| `decisions` | Decision artifacts / summaries |
| `alerts` | Operator alerts |
| `job_runs` | Background/job execution records |
| `audit_events` | Security/ops audit trail |

Minimal columns: `id`, created/updated timestamps, entity keys as needed, `payload` JSON where flexible fields are required.

Migrations: Alembic (`chakraops/alembic.ini`) when installed.

## Legacy / transitional stores (do not delete first)

Inventoried by `migrate_sqlite_inventory` — examples:

| Store | Role |
|-------|------|
| `data/journal.db` | Manual journal (unique history — preserve) |
| `data/account.db` / holdings | Manual portfolio (fallback until R53) |
| `data/ticket_queue_r42.db` | Today ticket queue |
| `data/broker_snapshots_r52.db` | R52 snapshot cache (when present) |
| `out/decision_latest.json` (+ related) | Runtime decision output |

Process: inventory → authoritative vs duplicate → backup outside git → import/reconcile → validate → switch reads → retire obsolete paths. Git history is the archive; no `archive/` graveyard for unique data.

## Research

Parquet datasets + DuckDB queries — [RESEARCH_DATA.md](./RESEARCH_DATA.md). Not for concurrent transactional writes.

## Live portfolio (post R52/R53)

When healthy, Robinhood read snapshot is primary live account/position source. Manual edit belongs under Recovery/Advanced, labeled non-live.
