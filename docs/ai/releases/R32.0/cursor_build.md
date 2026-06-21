# CURSOR BUILD — R32.0

Trigger: `CURSOR BUILD R32.0`

1. Read `AGENTS.md`, `docs/ai/MASTER_CONTROL.md`, and `RELEASE_PACKET.md`.
2. Verify repo root, branch `release/R31-R35-program`, and clean/expected status.
3. Read current source and tests before editing.
4. Implement workstreams in packet order.
5. Use ORATS only through existing approved clients; redact tokens.
6. Add or update tests for changed behavior.
7. Run all mandatory gates and release-specific validation.
8. Write local evidence to `out/verification/R32.0/`.
9. Update `STATUS.md` and `TOOL_LOG.md`.
10. Return a STEP report and stop before commit unless explicitly authorized.

Do not invent scope. Do not use broker execution. Do not hide missing data.
