# Prompt 02 — Claude Code Review

**Phase:** CLAUDE REVIEW  
**Used by:** Claude Code

---

## Instructions

1. Read `AGENTS.md` and `CLAUDE.md`.
2. Read `docs/ai/releases/<Release>/RELEASE_PACKET.md` in full.
3. Read `docs/ai/releases/<Release>/claude_review.md` for release-specific review focus.
4. Run `git diff main...release/<Release>` (or equivalent) to inspect all changes on this branch.
5. Review against the packet:
   - Scope: does every change fall within allowed files?
   - Non-goals: does anything violate the forbidden list?
   - Trading safety: does any change affect trading logic, ORATS, broker integration, or automated execution?
   - Artifact safety: are `out/`, `data/`, runtime JSON, or UI label rules respected?
   - Gate evidence: do gate results in STATUS.md match the release baseline?
6. Return verdict: **APPROVED** / **APPROVED WITH NOTES** / **BLOCKED** with findings.

**Do not implement. Do not modify any file. Do not update TOOL_LOG.md or STATUS.md. Do not commit.**

The operator or a subsequent explicit recording step (e.g., RECORD MERGE) will copy the verdict into TOOL_LOG.md.

---

## Template Values

| Placeholder | Meaning |
|-------------|---------|
| `<Release>` | Release identifier |
| `<Branch>` | Git branch |
| `<Objective>` | Release goal |
| `<Allowed files>` | Files permitted to change |
| `<Forbidden files>` | Files that must not change |
| `<Gates>` | Expected gate results |
| `<Review level>` | Level 2, 3, or 4 |

---

## Stop Conditions

- BLOCKED verdict → report clearly and wait for operator resolution
- Unexpected trading logic change → BLOCK immediately
- Broker or auto-trading proposal → BLOCK immediately
