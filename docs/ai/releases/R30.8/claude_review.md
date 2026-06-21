# Claude Code Review Instructions — R30.8

## Status

**Not required by default for R30.8 (Level 1 — docs/governance).**

Use only if:
- Codex returns a BLOCKED verdict, or
- Operator explicitly escalates to Level 2+ review.

## If Escalated

1. Read `AGENTS.md` and `CLAUDE.md`.
2. Read `docs/ai/releases/R30.8/RELEASE_PACKET.md` in full.
3. Run `git diff main...release/R30.8` to inspect all changes.
4. Verify:
   - All changed files are in the Allowed Files list.
   - No source code, tests, runtime files, or workflow files were touched.
   - Docs content is accurate and consistent with existing governance docs.
   - No trading-safety rules violated.
5. Return verdict: **APPROVED** / **APPROVED WITH NOTES** / **BLOCKED** with findings.

## Stop Point

Do not implement. Do not modify any file. Do not update TOOL_LOG.md or STATUS.md. Do not commit. The operator copies the verdict into TOOL_LOG.md.
