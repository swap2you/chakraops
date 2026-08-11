# Data Model — ChakraOps (canonical)

**R51 foundation:** `chakraops/app/core/data_platform/`  
**Detail contracts:** `chakraops/docs/DATA_CONTRACT.md` (ORATS/eval semantics)  
**R70 honesty:** `runtime_persistence_inventory()` — Postgres URL gate ≠ LIVE portfolio SoT.

## Platform engine (SQLAlchemy) — scaffolded + production URL gate

Prefer `DATABASE_URL=postgresql+psycopg://...` in production (R62 fail-closed gate). Local default: SQLite file under `chakraops/data/chakraops_platform.db`.

**Important (R70-DEF-030):** This engine hosts *scaffolded* models. Critical LIVE broker/portfolio/ticket paths still write **SQLite/JSON** stores listed below. Do not claim Postgres is portfolio/broker SoT until those stores are migrated.

| Table (scaffolded) | Purpose |
|-------|---------|
| `broker_accounts` | Broker account aliases / metadata (no full account numbers in logs/evidence) |
| `broker_snapshots` | Planned point-in-time snapshots (runtime still uses `broker_snapshots_r52.db`) |
| `positions_normalized` | Planned canonical positions |
| `journal_fills` | Planned journal rows |
| `tickets` | Planned ticket queue |
| `universe_lifecycle` | Universe membership / lifecycle events |
| `decisions` | Decision artifacts / summaries |
| `alerts` | Operator alerts |
| `job_runs` | Background/job execution records |
| `audit_events` | Security/ops audit trail |

Migrations: Alembic (`chakraops/alembic.ini`) when installed.

## Runtime SoT (current — SQLite / JSON)

| Store | Role / authority |
|-------|------------------|
| `data/broker_snapshots_r52.db` (+ JSON sidecar) | **LIVE** last-good broker read |
| `out/account.db` / holdings | Recovery/manual entry — **not** LIVE |
| `data/positions.db` (unified) | Derived mirror / repair surface |
| `data/ticket_queue_r42.db` | Manual ticket queue |
| `data/journal.db` | Manual journal history |
| `out/decision_latest.json` (+ eval snapshot) | LIVE decision artifact |
| `artifacts/positions/open_positions.json` | Legacy ledger (non-authoritative vs broker) |

## Store sprawl (R70-DEF-031) — DEFERRED

Collapsing six overlapping position/portfolio stores is **DEFERRED (XL)**: multi-DB + repair/reconcile endpoints are tightly coupled; safe consolidation requires a sequenced migration after DEF-030 Postgres cutover. Authority matrix above is the interim contract.

## Research

Parquet datasets + DuckDB queries — [RESEARCH_DATA.md](./RESEARCH_DATA.md). Not for concurrent transactional writes.

## Live portfolio (post R52/R53)

When healthy, Robinhood read snapshot is primary live account/position source. Manual edit belongs under Recovery/Advanced, labeled non-live.
