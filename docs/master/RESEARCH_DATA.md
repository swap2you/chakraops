# Research Data Conventions — Parquet + DuckDB

**Audience:** Strategy Lab, backtests, stress matrices, analytical exports.  
**Not for:** Multi-process transactional production writes (use SQLAlchemy/Postgres — [DATA_MODEL.md](./DATA_MODEL.md)).

## Rules

1. **Parquet** is the on-disk research format (columnar, versionable under `out/research/` or explicit project paths).
2. **DuckDB** is for local analytical queries over Parquet — single-writer research sessions only.
3. Do **not** use DuckDB as the shared mutable store for API workers, monitors, or broker sync.
4. Label all research outputs **SIMULATION** when surfaced near live recommendations.
5. No secrets in research trees; redact account identifiers.

## Suggested layout

```
out/research/
  <dataset>/
    *.parquet
    manifest.json    # schema version, as-of, source release
```

## Dependencies

Optional: `duckdb>=1.0`, `pyarrow>=14` (see `chakraops/requirements.txt`).

## Relation to production

Transactional tables (journal, tickets, snapshots, decisions) stay in Postgres/SQLite via `data_platform`. Export to Parquet for offline analysis; never reverse that for live writes.
