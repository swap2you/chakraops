# Prompt 03 — Codex Review

**Phase:** CODEX REVIEW  
**Used by:** Codex

---

## Instructions

1. Read `AGENTS.md`.
2. Read `docs/ai/releases/<Release>/RELEASE_PACKET.md` in full.
3. Read `docs/ai/releases/<Release>/codex_review.md` for release-specific review focus.
4. Inspect the diff for this branch against `main`.
5. Verify independently:
   - Every changed file is in the allowed-files list.
   - No file outside the allowed list was touched.
   - Non-goals are respected (no code/runtime/test/trading changes if this is a docs release).
   - Scope is consistent with the packet objective.
   - No forbidden tokens (`FAIL_`, `WARN_`, `PASS`) appear in UI-facing output.
   - No runtime files under `out/` or `data/` were modified.
6. Return verdict: **APPROVED** / **APPROVED WITH NOTES** / **BLOCKED** with findings.

**Do not implement. Do not modify any file. Do not update TOOL_LOG.md or STATUS.md. Do not commit.**

The operator or a subsequent explicit recording step will copy the verdict into TOOL_LOG.md.

---

## Template Values

| Placeholder | Meaning |
|-------------|---------|
| `<Release>` | Release identifier |
| `<Branch>` | Git branch |
| `<Objective>` | Release goal |
| `<Allowed files>` | Files permitted to change |
| `<Forbidden files>` | Files that must not change |
| `<Gates>` | Expected gate results (if applicable) |
| `<Review level>` | Level 1–4 |

---

## Stop Conditions

- Any change outside allowed files → BLOCK immediately
- Any trading or runtime change in a docs release → BLOCK immediately
- Verdict BLOCKED → report clearly and wait for operator resolution
