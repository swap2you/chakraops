# ChakraOps Documentation and Non-Functional Cleanup Report

**Date:** 2026-02-06  
**Scope:** Documentation consolidation, legacy containment, out/ hygiene. No strategy, API, or behavior changes.

---

## 1. What Was Consolidated

### Documentation (PART 1)

- **docs/README.md** — Single entry point: what ChakraOps is; explicit “Start with RUNBOOK.md if operating the system”; links to RUNBOOK, ARCHITECTURE, DATA_CONTRACT, history.
- **docs/RUNBOOK.md** — Expanded with:
  - **Section 7 — Operator Playbook: What To Do When Something Looks Wrong:** Prerequisites checklist, startup sequence, daily workflow (what runs, what files are produced), smoke tests (exact commands), debug decision tree (Symbol BLOCKED, UNKNOWN risk, No opportunities, UI vs backend), key files to inspect, what NOT to do.
  - **Section 9 — Housekeeping:** Archiving `out/` procedure: keep last 14 or 30 days hot, archive older to `out/archive/` via `tools/archive_out.py`; command and options documented.
- **docs/ARCHITECTURE.md** — Focus limited to evaluation pipeline, strategy model, risk & gating flow, decision lifecycle. Intro states it contains no operational instructions.
- **docs/DATA_CONTRACT.md** — Explicit note added: “Overrides cannot bypass required missing data.”
- **docs/history/** — All phase summaries, validation reports, and historical design docs moved here; **docs/history/README.md** states these are historical and not required for operation.

### Files Moved to docs/history/

- PHASE5_STRATEGY_AND_ARCHITECTURE.md  
- PHASE5_PRECONDITIONS.md (already in history)  
- PHASE6_VALIDATION_REPORT.md (already in history)  
- PHASE7_* (summaries, cleanup, quick reference, refactor, validation) (already in history)  
- STRATEGY_OVERVIEW.md  
- strategy_audit.md  
- strategy_validation.md  
- DOCS_AUDIT.md  
- RUNBOOK_EXECUTION.md  
- RUNTIME_SMOKE.md  
- LIVE_DEBUG_REPORT.md  
- VALIDATION_AND_TESTING.md  

---

## 2. What Was Moved (Legacy — PART 2)

- **chakraops/legacy/** — New top-level directory with:
  - **legacy/README.md** — States: not used by current pipeline; kept for reference; not exercised by tests or runtime.
  - **legacy/thedata/** — Copy of ThetaTerminal v3 JAR and lib (from `app/thedata/`). Original left in place to avoid breaking any manual JAR run; legacy copy is the documented reference location.
  - **legacy/scripts/** — Theta-only scripts moved here (originals removed from `scripts/`):
    - debug_theta_spy_expirations.py  
    - smoke_thetadata_real.py  
    - smoke_thetadata_v3.py  
    - theta_v3_smoketest.py  

- **Not moved (still in app/ or tools/):** ThetaTerminal HTTP provider, ThetaData provider, theta options adapter, and tools (theta_shadow_signals, thetadata_capabilities, thetadata_probe) remain in place because they are imported by the live UI path (e.g. dashboard, live_market_adapter). The **evaluation pipeline** is ORATS-only; legacy/ holds only artifacts and scripts that are not on the evaluation or CI path.

---

## 3. What Remains Legacy

- **chakraops/legacy/** — ThetaTerminal JAR (and lib), Theta-only smoke/debug scripts. Not used by the current evaluation pipeline or by CI/tests.
- **app/thedata/** — Still present (JAR/lib) for any manual ThetaTerminal server use; legacy/ holds a reference copy.
- Optional live UI / shadow code (ThetaTerminal provider, ThetaData provider, theta adapter, theta_shadow_signals, etc.) remains in `app/` and `tools/` for backward compatibility; it is not part of the authoritative evaluation path.

---

## 4. Out/ Directory Hygiene (PART 3)

- **tools/archive_out.py** — Script that moves evaluation run JSONs (and _data_completeness sidecars) older than `--keep-days` (default 30) from `out/evaluations/` to `out/archive/YYYY-MM/`. Never archives `latest.json` or the run it points to. Supports `--dry-run`.
- **RUNBOOK.md Section 9 (Housekeeping)** — Procedure documented: run `python tools/archive_out.py --keep-days 30` from chakraops; optional weekly/cron; non-destructive (move, not delete).

---

## 5. Confirmation: No Behavior Changed

- **Strategy / risk / scoring / APIs / UI:** No changes.  
- **Tests:** No test logic or assertions changed; only documentation and non-runtime artifacts (legacy moves, archive script) were added or moved.  
- **Broker automation:** Not introduced; RUNBOOK and playbook reiterate that execution is manual.  
- **Historical content:** No deletion; phase and historical docs were moved to docs/history/, not removed.

---

## 6. Validation

- No live ORATS was run.  
- Tests: run `python -m pytest tests/ -v --tb=short` from chakraops to confirm green (recommended post-merge).  
- Documentation links: README → RUNBOOK, ARCHITECTURE, DATA_CONTRACT, history; RUNBOOK → Housekeeping and tools/archive_out.py; all targets exist.
