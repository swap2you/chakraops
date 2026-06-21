# Codex Review Instructions — R30.8

## Command

```
CODEX REVIEW R30.8
```

## Instructions

1. Read `AGENTS.md`.
2. Read `docs/ai/releases/R30.8/RELEASE_PACKET.md` in full.
3. Inspect the diff for `release/R30.8` against `main`.
4. Verify independently:
   - Every changed file is in the Allowed Files list.
   - No file outside the allowed list was touched.
   - Non-goals are respected: no code, no tests, no runtime, no trading logic, no workflows.
   - All new docs content is consistent and non-contradictory.
   - No forbidden tokens (`FAIL_`, `WARN_`, `PASS`) in UI-facing output.
   - `out/` and `data/` untouched.
5. Return verdict: **APPROVED** / **APPROVED WITH NOTES** / **BLOCKED** with findings.

## Focus Areas

- Scope containment: did Cursor stay within allowed files?
- Content accuracy: are the prompt templates and operating model internally consistent?
- Safety: does anything in the AI library accidentally weaken AGENTS.md trading safety rules?
- Traveler: does the roadmap correctly state no auto-trading or broker execution releases exist?

## Stop Point

Do not implement. Do not modify any file. Do not update TOOL_LOG.md or STATUS.md. Do not commit. The operator copies the verdict into TOOL_LOG.md.
