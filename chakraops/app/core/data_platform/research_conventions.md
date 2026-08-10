# Research conventions (package pointer)

Canonical doc: `docs/master/RESEARCH_DATA.md`

- Parquet on disk for research datasets / backtests / stress matrices.
- DuckDB for local analytical queries over Parquet.
- Do **not** use DuckDB as multi-process transactional production storage.
- Production transactional writes → SQLAlchemy (`db.py` / Postgres or local SQLite).
