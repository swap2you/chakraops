# R51 Acceptance — Baseline Reconciliation + Data Platform

## Status
`R51_IN_PROGRESS` (docs + data platform foundation + quality capture)

## IDs

| ID | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| R51-D1 | Canonical docs under `docs/master/` (PRODUCT_REQUIREMENTS, ARCHITECTURE, CURRENT_STATE, OPERATOR_RUNBOOK, PRODUCTION_RUNBOOK, DATA_MODEL, SECURITY, RELEASE_ROADMAP, RESEARCH_DATA) | **PASS** | `docs/master/*.md` |
| R51-D2 | CURRENT_STATE reflects R51–R60 active, baseline `32e0449`, R41–R50 technically complete | **PASS** | `docs/master/CURRENT_STATE.md`, `docs/ai/PROGRAM_STATUS.md` |
| R51-C8 | Broker status docs: NO_GO historical; current target `ROBINHOOD_MCP_READ_ONLY_AVAILABLE` / UNAUTHENTICATED | **PASS** | `chakraops/docs/RUNBOOK_OPERATOR_DAILY.md` §5; CURRENT_STATE broker section; keep `docs/ai/releases/R37/R37_NO_GO.md` |
| R51-P1 | Data platform `db.py` resolves `DATABASE_URL` (Postgres preferred) else local SQLite | **PASS** | `app/core/data_platform/db.py`; `tests/test_r51_data_platform.py` |
| R51-P2 | SQLAlchemy models for broker/journal/tickets/universe/decisions/alerts/jobs/audit | **PASS** | `app/core/data_platform/models_sql.py` |
| R51-P3 | Alembic scaffold + initial migration | **PASS** | `chakraops/alembic.ini`, `alembic/env.py`, `alembic/versions/r51_001_initial_data_platform.py` |
| R51-P4 | Read-only SQLite/JSON inventory tooling | **PASS** | `app/core/data_platform/migrate_sqlite_inventory.py` |
| R51-P5 | Research conventions (Parquet+DuckDB, not transactional) | **PASS** | `docs/master/RESEARCH_DATA.md`, `app/core/data_platform/research_conventions.md` |
| R51-P6 | requirements append: sqlalchemy, alembic, psycopg, duckdb, pyarrow | **PASS** | `chakraops/requirements.txt` |
| R51-Q1 | Quality evidence capture script | **PASS** | `scripts/capture_quality_logs_r51.py` → `out/verification/R51/quality/` |
| R51-R1 | No unexpected Today 404 (ticket-queue routes present; restart if stale process) | **PASS** | Prior fix + e2e 4xx capture; routes already in backend |
| R51-R2 | React Router future flags / orphan CommandBar-Palette removed | **PASS** | `frontend/src/app/App.tsx`; deleted components; `generate_r41_screen_contract.py` REMOVED_R51 |
| R51-R3 | CONTROL_INVENTORY `unit_or_pending` → 0 pending | **PASS** | `docs/ai/releases/R41/CONTROL_INVENTORY.csv` |
| R51-S1 | Safety: no broker writes; R52 package not rewritten by R51 | **PASS** | R51 scope limited; broker under R52 parallel |

## Tests

```text
pytest tests/test_r51_data_platform.py -q
python ../scripts/capture_quality_logs_r51.py
```

## Notes / PARTIAL

| ID | Note |
|----|------|
| R51-MIG | Full Postgres cutover + import of legacy journal/account DBs is **deferred** to R53 migration work; R51 delivers foundation + inventory only → **PARTIAL** for end-to-end store retirement |
| R51-CLEAN | Broad HEAD doc clutter deletion deferred when unsafe; git history remains archive → **PARTIAL** |

## Do not claim

R52+ complete. Independent R41–R50 Codex/Cowork acceptance (deferred to R60). Broker write capability.
