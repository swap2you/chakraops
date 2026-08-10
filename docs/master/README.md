# ChakraOps Master Documentation

This directory holds the **single source of truth** for product scope, roadmap, release process, backlog, and cleanup for the next 12 months.

| Document | Purpose |
|----------|---------|
| [**PRODUCT_REQUIREMENTS.md**](./PRODUCT_REQUIREMENTS.md) | Canonical product requirements (R51+); points to Master PRD for detail. |
| [**ARCHITECTURE.md**](./ARCHITECTURE.md) | Canonical stack, broker boundary, data platform. |
| [**CURRENT_STATE.md**](./CURRENT_STATE.md) | Live program status (R51–R60 active). |
| [**OPERATOR_RUNBOOK.md**](./OPERATOR_RUNBOOK.md) | Pointer to daily operator runbook. |
| [**PRODUCTION_RUNBOOK.md**](./PRODUCTION_RUNBOOK.md) | Production-mode start, env, data, broker auth. |
| [**DATA_MODEL.md**](./DATA_MODEL.md) | Transactional tables + legacy store inventory policy. |
| [**SECURITY.md**](./SECURITY.md) | Secrets, broker read-only contract, app safety. |
| [**RELEASE_ROADMAP.md**](./RELEASE_ROADMAP.md) | R51–R60 connected production roadmap. |
| [**RESEARCH_DATA.md**](./RESEARCH_DATA.md) | Parquet + DuckDB research conventions. |
| [**CHAKRAOPS_MASTER_PRD.md**](./CHAKRAOPS_MASTER_PRD.md) | Full Master PRD: charter, personas, pillars, acceptance. |
| [**ROADMAP_2026.md**](./ROADMAP_2026.md) | Legacy phased roadmap (historical; superseded for execution by RELEASE_ROADMAP). |
| [**RELEASE_PLAYBOOK.md**](./RELEASE_PLAYBOOK.md) | Exact SDLC gate steps, how to record outputs in `out/verification/<Release>/notes.md`, UAT, rollback, Definition of Done. |
| [**BACKLOG.md**](./BACKLOG.md) | Prioritized backlog: Epics → Stories → Tasks; value, risk, dependencies, acceptance criteria, test notes; must-have vs nice-to-have. |
| [**CLEANUP_POLICY.md**](./CLEANUP_POLICY.md) | Repo bloat categories, keep vs delete rules, `docs/archive/` approach, safe cleanup checklist. |

**Related (outside this dir):**

- **Release checklist and release notes:** `chakraops/docs/releases/RELEASE_CHECKLIST.md`, `chakraops/docs/releases/<Release>_release_notes.md`, `chakraops/docs/releases/<Release>_requirements.md`.
- **Verification evidence:** `out/verification/<Release>/notes.md` (gate outputs and UAT).

Use the master PRD and roadmap for scope and prioritization; use the playbook and backlog for execution and release discipline.
