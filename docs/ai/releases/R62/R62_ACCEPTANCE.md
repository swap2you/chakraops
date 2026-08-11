# R62 Acceptance — PostgreSQL production URL gate

## Status

`R62_TECHNICALLY_COMPLETE` for **URL gate** (remote Postgres on VPS pending owner provision).

**R70 honesty demotion (DEF-030):** R62 is *not* a full portfolio/broker SoT cutover. Critical stores (`broker_snapshots_r52`, holdings, positions_unified, tickets, decision JSON) remain SQLite/JSON. See `runtime_persistence_inventory()` and `docs/master/DATA_MODEL.md`.

| ID | Result |
|----|--------|
| R62-A1 Production fails without Postgres URL | PASS |
| R62-A2 Production rejects SQLite | PASS |
| R62-A3 Local/dev SQLite still allowed | PASS |
| R62-A4 Startup gate in API lifespan | PASS |
| R62-A5 Journal history preserved | PASS (no delete) |
| R70-H1 Postgres claimed as portfolio SoT | FAIL → demoted; honesty inventory asserts False |

Remote DB instance / critical-store migration on VPS: OWNER_ACTION / DEFERRED_XL.
