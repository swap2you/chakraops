# Phase 0 / 0.5 Keep List — Surgical Cleanup

**Proof method:** Ripgrep for imports/references; no Python code imports from `legacy` package or `legacy/` path.

---

## KEEP (must remain)

| Path | Reason |
|------|--------|
| `app/` | Core application; no deletions under app/ unless provably unused |
| `config/` | universe.csv, runtime.yaml, scoring.yaml, alerts.yaml |
| `main.py` | Entrypoint; referenced in docs |
| `tests/_core/` | Default testpaths in pytest.ini; core behavior |
| `tests/fixtures/` | Used by _core and other tests |
| `tests/__init__.py` | Package marker |
| `tests/legacy/` | Only `__init__.py`; norecursedirs in pytest.ini references "legacy" |
| `pytest.ini` | Defines testpaths, norecursedirs |
| `config.yaml.example`, `.env.example` | Config templates |
| `tools/` (except moved to legacy_disabled) | Archive/benchmark/seed scripts |
| `ChakraOps_Core_Watchlist.csv`, `ARCHITECTURE.md`, `BASELINE_BOOKMARK.md` | Project metadata |
| `artifacts/` | Folder structure; validation and harness outputs |

**Docs kept (exact list after Phase 0.5):**
- `docs/README.md`
- `docs/RUNBOOK_EXECUTION.md`
- `docs/ORATS_API_Reference.md`
- `docs/orats_endpoint_matrix.md`
- `docs/phase0_keep_list.md`
- `docs/DATA_CONTRACT.md`
- `docs/data_dependencies.md`

**Scripts kept:**
- `scripts/validate_one_symbol.py`
- `scripts/orats_harness.py`
- `scripts/run_api.py`
- `scripts/orats_smoke.py` (referenced in RUNBOOK_EXECUTION.md)

---

## DELETED (Phase 0)

| Path | Proof |
|------|--------|
| `legacy/` (entire directory) | No imports reference it. ThetaData JARs and scripts not used by ORATS pipeline. |

---

## DELETED (Phase 0.5)

| Path | Reason |
|------|--------|
| `docs/history/` | Entire directory (phase reports, runbook copy, audits). RUNBOOK_EXECUTION.md copied to docs/ root. |
| `docs/tests/` | SKIPPED_TESTS etc.; not in keep list. |
| `tests/_archived/` | Entire directory (archived tests). |
| `tests/_archived_theta/` | Entire directory (ThetaData provider tests). |
| Docs: PHASE*.md, *_REPORT*.md, *_SUMMARY*.md, *AUDIT*.md, *SMOKE*.md, STRATEGY_*.md, VALIDATION_*.md, DOCS_CLEANUP*.md, RUNBOOK.md, and all others not in docs kept list above. | Aggressive doc purge per Phase 0.5. |

---

## MOVED TO legacy_disabled (Phase 0.5)

| Location | Items |
|----------|--------|
| `scripts/legacy_disabled/` | All scripts except validate_one_symbol.py, orats_harness.py, run_api.py, orats_smoke.py (e.g. capture_snapshot_amd.py, debug_orats_*.py, diff_signals.py, live_dashboard.py, smoke_*.py, run_once.py, run_pipeline_loop.py, run_signals.py, view_dashboard.py, etc.). |
| `tools/legacy_disabled/` | theta_shadow_signals.py, thetadata_capabilities.py, thetadata_probe.py (ThetaData-related; we are not using ThetaData). |

---

## Do NOT delete

- Anything under `app/` without proof of non-use.
- `tests/legacy/` directory (pytest norecursedirs expects it).
- The seven docs listed in "Docs kept" above.
