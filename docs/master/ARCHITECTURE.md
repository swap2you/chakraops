# Architecture — ChakraOps (canonical)

**Last updated:** 2026-08-10 (R51)

## Stack

| Layer | Tech | Ports |
|-------|------|-------|
| Frontend | React + Vite SPA | `18873` |
| Backend | FastAPI (`chakraops/app`) | `18800` |
| Market data | ORATS (options/strategy) | — |
| Live portfolio (R52+) | Robinhood MCP **read-only** client | — |
| Transactional data (R51+) | SQLAlchemy platform engine; **Postgres URL mandatory in production (gate only)**; critical LIVE portfolio/broker stores remain SQLite/JSON until migrated (R70-DEF-030) | `DATABASE_URL` |
| Research | Parquet + DuckDB (analytical only) | see [RESEARCH_DATA.md](./RESEARCH_DATA.md) |

## Layout (keep)

```
chakraops/                 # backend package root
  app/api/                 # HTTP routes
  app/core/                # eval, wheel, ops, broker, data_platform, …
  config/                  # YAML / allowlists
  data/                    # local SQLite / operator stores (not secrets)
frontend/                  # SPA
docs/master/               # product/governance truth
out/verification/<Rel>/    # evidence (gitignored)
```

## Broker boundary (R52)

- Narrow `BrokerReadProvider` — **no** generic `call_robinhood_tool`.
- Source-controlled read allowlist + write denylist tests.
- Status: `ROBINHOOD_MCP_READ_ONLY_AVAILABLE` when token configured; else `UNAUTHENTICATED` / `ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER`.
- Historical R37 `NO_GO` docs remain archive; not current runtime target.

## Data platform (R51 / R70 honesty)

- Package: `app/core/data_platform/`
- Models: accounts, snapshots, positions, journal fills, tickets, universe lifecycle, decisions, alerts, job runs, audit events (**scaffolded**).
- Production: `DATABASE_URL` must be PostgreSQL (R62 gate). This does **not** mean broker/portfolio SoT is Postgres yet.
- Runtime LIVE SoT: see [DATA_MODEL.md](./DATA_MODEL.md) (`broker_snapshots_r52.db`, decision JSON, etc.).
- Legacy SQLite/JSON under `data/` and `out/` are inventoried before migration — do not delete unique journal/history.
- Store consolidation (R70-DEF-031): **DEFERRED** pending sequenced migration.

## Safety architecture

Manual ticket only · trade_execution=false · scheduler off · ORATS for strategy · broker reads fail closed when stale · Stay in Cash valid.

## Related maps

[REPO_ARCHITECTURE_MAP.md](./REPO_ARCHITECTURE_MAP.md) · [DATA_MODEL.md](./DATA_MODEL.md) · [SECURITY.md](./SECURITY.md)
