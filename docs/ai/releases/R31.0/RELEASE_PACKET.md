# RELEASE_PACKET â€” R31.0

## Release

R31.0

## Branch

release/R31.0 â€” **not created yet; create from main after R30.8 merges**

## Objective

Conduct a read-only repository and product baseline audit: architecture, trading decision model, data/database, frontend, jobs, notifications, tech stack, and future security/hosting readiness. Produce audit documentation after approval.

## Risk Level

Level 2 â€” repo-wide audit/planning

---

## Scope

- Audit backend architecture (`chakraops/app/`)
- Audit frontend architecture (`frontend/src/`)
- Audit trading decision model (eligibility, scoring, readiness, PnL)
- Audit data / database / reporting layer
- Audit jobs and scheduling
- Audit notifications and alert system
- Audit tech stack (Python, FastAPI, React, Vite, SQLite)
- Audit future security and hosting readiness
- Produce audit documentation in the exact files listed in the Allowed Files section only. Any additional file requires operator approval and a release packet update before implementation begins.

## Non-Goals

- No code changes
- No runtime changes
- No tests unless explicitly approved by operator
- No implementation of any findings
- No trading-logic changes
- No broker integration
- No database schema changes
- No scheduler changes
- No GitHub Actions changes
- No deployment changes

## Allowed Files

Tracked files permitted to change:

- `docs/master/R31.0_REPOSITORY_PRODUCT_BASELINE_AUDIT.md`
- `docs/master/R31.0_ROADMAP_RECOMMENDATIONS.md`
- `chakraops/docs/releases/R31.0_requirements.md`
- `chakraops/docs/releases/R31.0_release_notes.md`
- `chakraops/docs/releases/RELEASE_CHECKLIST.md`
- `docs/master/CURRENT_STATE.md`
- `docs/ai/releases/R31.0/STATUS.md`
- `docs/ai/releases/R31.0/TOOL_LOG.md`

Allowed ignored local evidence:

- `out/verification/R31.0/notes.md`

## Forbidden Files

- All backend source files (`chakraops/app/`)
- All frontend source files (`frontend/src/`)
- All test files (`chakraops/tests/`)
- ORATS logic
- Trading logic
- Database files
- Scheduler files
- GitHub Actions (`.github/`)
- Runtime files under `out/` (except `out/verification/R31.0/notes.md`)
- `data/`
- Deployment files

---

## Implementation Steps

1. Create branch `release/R31.0` from `main`.
2. Read this packet and all existing architecture docs.
3. Audit each domain listed in scope.
4. Produce audit notes per domain.
5. Produce a summary audit document.
6. Update STATUS.md and TOOL_LOG.md.
7. Return STEP report.

## Verification Gates

The AGENTS.md baseline gates are mandatory before DONE. Level 2 review adds review expectations but cannot remove these gates. Manual UAT is not required for R31.0 (audit/planning only â€” no UI or code behavior change), unless explicitly added by the operator.

- [ ] Backend: `cd chakraops && python -m pytest tests -q --tb=short`
- [ ] Frontend tests: `cd frontend && npm run test -- --run`
- [ ] Frontend build: `cd frontend && npm run build`
- [ ] Git diff scope check: only exact Allowed Files changed; no source/runtime files modified
- [ ] Operator review of audit findings
- [ ] Evidence: `out/verification/R31.0/notes.md`

## Review Requirements

- Cursor: required (audit execution)
- Claude Code: recommended (architecture perspective)
- Codex: required (scope containment verification)

---

## PR Title

R31.0 â€” Repository and product baseline audit

## Rollback

Rollback tag: `chakraops-r30.8.0`

Rollback: delete all audit documentation created in this release.

---

## Stop Point

Cursor produces audit docs only. No code changes. Operator reviews findings before any implementation planning begins.

