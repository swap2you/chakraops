# ChakraOps Repo Architecture Map

**Purpose:** Single reference for repo layout, what to keep, archive candidates, and where to add new docs/tests.  
**Alignment:** CLEANUP_POLICY.md, RELEASE_CHECKLIST.md, CHAKRAOPS_MASTER_PRD.md.  
**R24.7.0:** Inventory + cleanup plan only; no deletions in this release.

---

## 1. Top-level tree (1–2 levels)

```
ChakraOps/
├── .github/              # CI/workflows
├── .venv/                 # (optional) venv at root
├── .vscode/               # Editor config
├── chakraops/             # Backend app + config + tests
│   ├── app/               # Python application (api, core, data, db, execution, market, models, notifications, signals, ui, web)
│   ├── config/            # Runtime YAML (alerts, runtime, scoring, universe.csv)
│   ├── data/              # Data files, overrides, delta_overrides
│   ├── docs/              # Backend-focused docs (runbooks, contracts, phase docs, releases)
│   ├── scripts/           # Operational scripts
│   ├── tests/             # Backend pytest (unit + integration)
│   ├── tools/             # Dev/tooling
│   └── out/               # Generated at runtime (gitignored)
├── docs/                  # Repo-level docs
│   ├── master/            # PRD, roadmap, playbook, backlog, cleanup policy, this map
│   ├── releases/         # Some release notes (see chakraops/docs/releases for canonical)
│   └── archive/           # (R24.7.0) Proposed for superseded docs; README scaffold only
├── frontend/              # React/Vite app
│   ├── public/
│   ├── scripts/
│   ├── src/               # Components, pages, api, layout
│   └── dist/              # Build output (gitignored)
└── out/                   # Shared runtime output (gitignored): decision_latest.json, verification/<Release>/, etc.
```

---

## 2. Major folder purpose (one-liner each)

| Path | Purpose |
|------|---------|
| `.github/` | CI and workflow definitions. |
| `chakraops/` | Backend: FastAPI app, eval pipeline, data layer, config, tests. |
| `chakraops/app/` | Application code: api, core (eval, next_action, wheel), data, db, market, notifications, signals, ui, web. |
| `chakraops/config/` | Runtime config: alerts.yaml, runtime.yaml, scoring.yaml, universe.csv. |
| `chakraops/data/` | Data files, delta_overrides.json, optional overrides. |
| `chakraops/docs/` | Backend and product docs: runbooks, DATA_CONTRACT, DECISION_STORE_CANONICAL, phase/legacy docs, **releases** (canonical). |
| `chakraops/scripts/` | Operational scripts (eval, proof, etc.). |
| `chakraops/tests/` | Pytest suite; fixtures under `tests/fixtures/`. |
| `docs/` | Repo-level documentation. |
| `docs/master/` | Master PRD, ROADMAP_2026, RELEASE_PLAYBOOK, BACKLOG, CLEANUP_POLICY, REPO_ARCHITECTURE_MAP. |
| `docs/releases/` | Some release notes (duplicates or symlink-style; canonical is chakraops/docs/releases/). |
| `docs/archive/` | Proposed location for superseded design/phase docs (no moves in R24.7.0). |
| `frontend/` | React/Vite SPA; src/pages, src/components, src/api. |
| `out/` | Runtime output: decision artifact, verification notes, evaluations, alerts, lifecycle, wheel_state (see whitelist below). |

---

## 3. Must keep (explicit paths)

- **Release evidence (DONE releases):** Every `chakraops/docs/releases/<Release>_release_notes.md` and `out/verification/<Release>/notes.md` referenced in RELEASE_CHECKLIST as DONE. Do not delete.
- **Master docs:** `docs/master/CHAKRAOPS_MASTER_PRD.md`, `docs/master/ROADMAP_2026.md`, `docs/master/RELEASE_PLAYBOOK.md`, `docs/master/BACKLOG.md`, `docs/master/CLEANUP_POLICY.md`, `docs/master/REPO_ARCHITECTURE_MAP.md`.
- **Checklist and template:** `chakraops/docs/releases/RELEASE_CHECKLIST.md`, `chakraops/docs/releases/RELEASE_NOTES_TEMPLATE.md`.
- **Active requirements:** `chakraops/docs/releases/<Release>_requirements.md` for R24.x / R25.x (in progress or recent).
- **Canonical design / ops:** `chakraops/docs/DECISION_STORE_CANONICAL.md`, `chakraops/docs/DATA_CONTRACT.md`, `chakraops/docs/RUNBOOK_EXECUTION.md`, `chakraops/docs/WHEEL_STATE.md`, `chakraops/docs/REASON_CODES.md`; root `RUNBOOK_EXECUTION.md` if referenced.
- **Test-referenced:** Any fixture or file imported/referenced by tests (grep before any delete).

---

## 4. Archive candidates (explicit paths + justification)

*Archived in R24.7.1; see [docs/archive/INDEX.md](../archive/INDEX.md) for old path → new path.*

| Current path (after R24.7.1) | Justification |
|------------------------------|---------------|
| `docs/archive/phase_plans/phase4_plan.md` | Legacy phase plan; superseded by ROADMAP_2026 and master PRD. |
| `docs/archive/phase_plans/PHASE_8_PLAN.md` | Legacy phase plan; superseded by ROADMAP_2026. |
| `docs/archive/phase_plans/phase4_eligibility.md` | Legacy eligibility doc; covered by DATA_CONTRACT and release requirements. |
| `docs/archive/phase_plans/PHASE_10_PORTFOLIO_COMPLETION.md` | Legacy phase doc; scope covered by R21.1/R23.0 and roadmap. |
| `docs/archive/phase_plans/PHASE_12_FILL_WORKFLOW.md` | Legacy phase doc; workflow covered by runbooks and R24.x. |
| `docs/archive/superseded/phase0_keep_list.md` | Superseded by CLEANUP_POLICY and this map; README link updated in R24.7.1. |
| `docs/archive/superseded/project_status_bookmark_through_R22_7.md` | Status bookmark; superseded by ROADMAP_2026 and RELEASE_CHECKLIST. |
| `docs/archive/audits/DELTA_GATE_FIX_SUMMARY.md` | One-off fix summary; historical only. |
| `docs/archive/audits/FRONTEND_BACKEND_WIRING_AUDIT.md` | One-off audit; historical only. |
| `docs/archive/audits/TEST_HYGIENE_INTEGRITY_AUDIT.md` | One-off audit; historical only. |
| `docs/archive/audits/AUDIT_REPORT.md` | One-off audit; historical only. |
| `docs/archive/releases_supporting_artifacts/R24.2_verification_notes_full.md` | Duplicate verification content; canonical evidence in out/verification/R24.2/notes.md. |
| `docs/archive/releases_supporting_artifacts/R24.2_verification_gate_outputs.md` | Duplicate gate outputs; canonical in out/verification/R24.2/notes.md. |
| `docs/archive/releases_supporting_artifacts/R24.3_verification_notes_full.md` | Duplicate verification content; canonical in out/verification/R24.3/notes.md. |
| `docs/archive/releases_supporting_artifacts/R24.4_verification_notes.md` | Duplicate verification content; canonical in out/verification/R24.4/notes.md. |
| `docs/archive/releases_supporting_artifacts/R24.5_verification_notes.md` | Duplicate verification content; R24.5 superseded by R24.5.1. |

---

## 5. Delete candidates (only if proven unused)

*R24.7.0: No deletions. Below: criteria and current status.*

- **Grep checks performed:** No Python or TypeScript/JavaScript imports or file references to the legacy phase docs (phase4_plan, PHASE_8_PLAN, phase4_eligibility, PHASE_10, PHASE_12), DELTA_GATE_FIX_SUMMARY, FRONTEND_BACKEND_WIRING_AUDIT, TEST_HYGIENE_INTEGRITY_AUDIT, or AUDIT_REPORT. So **code does not depend on them**.
- **Doc references:** `chakraops/docs/README.md` was updated in R24.7.1 to point to CLEANUP_POLICY/REPO_ARCHITECTURE_MAP and archived phase0_keep_list.
- **Conclusion:** No path is listed as "delete" in this release. Any future delete must: (1) grep codebase for references, (2) grep docs for links, (3) prefer archive over delete per CLEANUP_POLICY.

---

## 6. Naming conventions + where to add new docs/tests

| Content | Location | Convention |
|---------|----------|-------------|
| **Release notes** | `chakraops/docs/releases/<Release>_release_notes.md` | e.g. R24.7.0_release_notes.md |
| **Release requirements** | `chakraops/docs/releases/<Release>_requirements.md` | e.g. R24.7.0_requirements.md |
| **Verification evidence** | `out/verification/<Release>/notes.md` | Gate outputs + UAT checklist; do not commit prose into decision artifacts |
| **Master/process docs** | `docs/master/<Name>.md` | PRD, roadmap, playbook, backlog, cleanup, this map |
| **Backend runbooks / contracts** | `chakraops/docs/<Name>.md` | RUNBOOK_*, DATA_CONTRACT, DECISION_STORE_CANONICAL |
| **New backend tests** | `chakraops/tests/` or `chakraops/tests/_core/` | test_<feature>_*.py; fixtures in tests/fixtures/ |
| **New frontend tests** | `frontend/src/**/*.test.tsx` or `*.test.ts` | Co-located or under src/pages, src/components |
| **Archive (future)** | `docs/archive/<category>/` | e.g. phase_plans/, audits/, superseded/ |

---

## 7. Where state lives (out/ whitelist summary) and what is safe to clean locally

- **Whitelist (from RELEASE_CHECKLIST):** `decision_latest.json`, `slack_status.json`, `universe_overrides.json`, `eval_snapshot.json`, `verification/<Release>/`, `evaluations/`, `alerts/`, `lifecycle/`, optional `mtf_cache/`, `wheel_state.json`.
- **Safe to clean locally:** Old runs in `artifacts/` (if present); prune decision archives per DECISION_ARCHIVE_MAX / DECISION_HISTORY_KEEP; trim `evaluations/`, `alerts/`, `lifecycle/` per retention policy. Do **not** remove `out/verification/<Release>/notes.md` for any DONE release.
- **Never commit:** `out/` contents, `.env`, secrets, API keys (see .gitignore).

---

*This map is the R24.7.0 repo inventory. Archive moves and deletes are planned in a later release per CLEANUP_POLICY.*
