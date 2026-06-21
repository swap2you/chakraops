# Codex Review Instructions — R31.0

## Command

```
CODEX REVIEW R31.0
```

## Instructions

1. Read `AGENTS.md`.
2. Read `docs/ai/releases/R31.0/RELEASE_PACKET.md` in full.
3. Inspect the diff for `release/R31.0` against `main`.
4. Verify independently:
   - Every changed file is a new audit documentation file.
   - No source code, tests, runtime files, or workflow files were modified.
   - Non-goals respected: no implementation, no code changes, no runtime changes.
   - Scope is consistent with the audit objective.
5. Return verdict: **APPROVED** / **APPROVED WITH NOTES** / **BLOCKED** with findings.

## Stop Point

Do not implement. Do not modify any file. Do not update TOOL_LOG.md or STATUS.md. Do not commit. The operator copies the verdict into TOOL_LOG.md.
