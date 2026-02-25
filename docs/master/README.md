# ChakraOps Master Documentation

This directory holds the **single source of truth** for product scope, roadmap, release process, backlog, and cleanup for the next 12 months.

| Document | Purpose |
|----------|---------|
| [**CHAKRAOPS_MASTER_PRD.md**](./CHAKRAOPS_MASTER_PRD.md) | Master Product Requirements: executive summary, charter, personas, daily workflow, pillars (A–F), guardrails, data/security, acceptance criteria. |
| [**ROADMAP_2026.md**](./ROADMAP_2026.md) | Phased execution roadmap: Phase 1–7 with milestones, scope, exit criteria; maps to releases R24.x / R25.x. |
| [**RELEASE_PLAYBOOK.md**](./RELEASE_PLAYBOOK.md) | Exact SDLC gate steps, how to record outputs in `out/verification/<Release>/notes.md`, UAT, rollback, Definition of Done. |
| [**BACKLOG.md**](./BACKLOG.md) | Prioritized backlog: Epics → Stories → Tasks; value, risk, dependencies, acceptance criteria, test notes; must-have vs nice-to-have. |
| [**CLEANUP_POLICY.md**](./CLEANUP_POLICY.md) | Repo bloat categories, keep vs delete rules, `docs/archive/` approach, safe cleanup checklist. |

**Related (outside this dir):**

- **Release checklist and release notes:** `chakraops/docs/releases/RELEASE_CHECKLIST.md`, `chakraops/docs/releases/<Release>_release_notes.md`, `chakraops/docs/releases/<Release>_requirements.md`.
- **Verification evidence:** `out/verification/<Release>/notes.md` (gate outputs and UAT).

Use the master PRD and roadmap for scope and prioritization; use the playbook and backlog for execution and release discipline.
