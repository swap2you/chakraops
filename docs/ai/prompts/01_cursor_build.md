# Prompt 01 — Cursor Build

**Phase:** CURSOR BUILD  
**Used by:** Cursor

---

## Instructions

1. Read `AGENTS.md` and `.cursor/rules/chakraops.mdc`.
2. Read `docs/ai/releases/<Release>/RELEASE_PACKET.md` in full.
3. Read `docs/ai/releases/<Release>/cursor_build.md` for release-specific instructions.
4. Confirm branch is `release/<Release>` and working tree is clean.
5. Implement **only** the scope defined in the packet. Do not expand.
6. Run all required gates defined in the packet:
   - Backend: `cd chakraops && python -m pytest tests -q --tb=short`
   - Frontend tests: `cd frontend && npm run test -- --run`
   - Frontend build: `cd frontend && npm run build`
7. Update `docs/ai/releases/<Release>/STATUS.md` — mark Cursor implementation done.
8. Update `docs/ai/releases/<Release>/TOOL_LOG.md` — add Cursor entry with files changed and gate results.
9. Return STEP report: files changed, tests run, gate summaries, skipped items, open risks, stop point.

**Stop before commit unless operator explicitly instructs in this message.**

---

## Template Values

| Placeholder | Meaning |
|-------------|---------|
| `<Release>` | Release identifier |
| `<Branch>` | Git branch |
| `<Objective>` | Release goal |
| `<Allowed files>` | Files permitted to change |
| `<Forbidden files>` | Files that must not change |
| `<Gates>` | Required gates for this release |
| `<Review level>` | Review tier per `docs/ai/REVIEW_POLICY.md` |

---

## Stop Conditions

- Scope expands beyond packet → STOP immediately
- Gate fails → STOP, report failure, do not proceed
- Unexpected file in `git status` → STOP, report
- Runtime files (`out/`, `data/`) modified → STOP
- Any trading-logic ambiguity → STOP
