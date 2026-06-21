# Prompt 05 — Merge and Tag

**Phase:** RECORD MERGE  
**Used by:** Cursor / Operator

---

## Instructions

After the operator merges the PR and creates the tag:

1. Read `docs/ai/releases/<Release>/STATUS.md`.
2. Update `STATUS.md`:
   - PR: `<PR number>`
   - Merge commit: `<short SHA>`
   - Tag: `<tag name>`
   - Current status: merged and tagged
3. Update `docs/master/CURRENT_STATE.md`:
   - Latest stable merged release: `<Release>`
   - Tag: `<tag>`
   - Current branch: (next release branch or `main`)
4. Update `chakraops/docs/releases/RELEASE_CHECKLIST.md`:
   - Mark all items checked for `<Release>`
   - Add Completion block: PR, merge commit, tag, gate summaries, review approvals
5. Return confirmation of all updates.

**Do not modify any source code. Do not run tests. Do not push.**

---

## Template Values

| Placeholder | Meaning |
|-------------|---------|
| `<Release>` | Release identifier |
| `<PR number>` | GitHub PR number |
| `<short SHA>` | First 7 chars of merge commit |
| `<tag name>` | e.g. `chakraops-r31.0.0` |
| `<rollback tag>` | Previous stable tag |
