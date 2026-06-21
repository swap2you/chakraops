# ChakraOps AI Review Policy

Defines the required review coverage for each release risk level.

**`AGENTS.md` is the root authority.** The baseline release gates defined in `AGENTS.md` — backend pytest, frontend tests, frontend build, and local verification evidence — are mandatory before any release is marked DONE, at every risk level. Risk levels may add extra gates and reviews; they cannot remove `AGENTS.md` baseline gates. Docs-only releases do not require additional trading or UAT gates, but they still follow the `AGENTS.md` baseline gate policy.

---

## Level 0 — Ledger / Doc Patch

**Examples:** Checklist sign-off, release ledger update, minor typo fix.

**Required:**
- Cursor implementation
- `git diff` operator spot-check
- AGENTS.md baseline gates (backend pytest, frontend tests, frontend build) before DONE
- Verification evidence: `out/verification/<Release>/notes.md`

**Not required:**
- Claude Code review
- Codex review
- Additional trading or UAT gates

---

## Level 1 — Docs / Governance

**Examples:** New documentation files, governance policies, AI library, release packets, known-issues updates.

**Required:**
- Cursor implementation
- Codex independent diff/scope review
- AGENTS.md baseline gates (backend pytest, frontend tests, frontend build) before DONE
- Verification evidence: `out/verification/<Release>/notes.md`

**Optional:**
- Claude Code review (operator may escalate if Codex blocks)

---

## Level 2 — Repo Hygiene

**Examples:** Runtime-file untracking, `.gitignore` updates, import cleanup, non-logic refactor.

**Required:**
- Cursor implementation
- Codex independent review
- AGENTS.md baseline gates (backend pytest, frontend tests, frontend build) before DONE
- Verification evidence: `out/verification/<Release>/notes.md`

**Optional:**
- Claude Code review for medium-complexity hygiene

---

## Level 3 — Code Refactor / Feature

**Examples:** New API endpoints, new frontend pages, new backend modules, significant refactor.

**Required:**
- Cursor implementation
- Claude Code architecture/review
- Codex independent diff review
- Full gates: backend pytest + frontend tests + frontend build
- Operator UAT
- Verification evidence: `out/verification/<Release>/notes.md`

---

## Level 4 — Trading Logic / Calculations

**Examples:** Decision pipeline changes, scoring model changes, eligibility logic, readiness checks, PnL calculations.

**Required:**
- Cursor implementation
- Claude Code architecture/review (mandatory)
- Codex independent diff review (mandatory)
- Full gates: backend pytest + frontend tests + frontend build
- Operator manual UAT with documented evidence
- Verification evidence: `out/verification/<Release>/notes.md`
- Extra caution: recommendations can affect real-money trading decisions

---

## Stop Conditions (All Levels)

Immediately stop and report to operator if:

- Unexpected files appear in `git status` outside allowed scope
- Any gate fails
- Scope expands beyond what the packet defines
- Runtime files under `out/` or `data/` are modified unexpectedly
- Trading logic behavior becomes unclear or ambiguous
- Any reviewer returns a **BLOCKED** verdict
- Any proposal introduces broker order execution or automated trading
