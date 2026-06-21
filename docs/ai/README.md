# ChakraOps AI Operating Library

This folder is the repo-native operating library for all AI tools working on ChakraOps.

## Purpose

Replace giant copied chat prompts with short launch commands that reference structured, version-controlled context files. Every release has a packet. Every tool has a log. The repo is the source of truth.

## What Lives Here

| Path | Purpose |
|------|---------|
| `docs/ai/OPERATING_MODEL.md` | Authority hierarchy, tool roles, short-command model |
| `docs/ai/REVIEW_POLICY.md` | Review levels by release risk |
| `docs/ai/QUICK_COMMANDS.md` | Copy-paste launch commands for every phase |
| `docs/ai/RELEASE_TRAVELER.md` | Living directional roadmap |
| `docs/ai/WORKFLOW_STATE_TEMPLATE.md` | Template for per-release STATUS.md files |
| `docs/ai/prompts/` | Reusable prompt templates (00–06) |
| `docs/ai/releases/` | Per-release folders: packet, status, tool log, tool prompts |

## Authority Order

1. `AGENTS.md` — root instruction file; all tools must read this first
2. `CLAUDE.md` — Claude-specific guidance
3. `.cursor/rules/chakraops.mdc` — Cursor-specific rules
4. `docs/ai/` — this operating library
5. Release packet (`docs/ai/releases/<Release>/RELEASE_PACKET.md`) — release scope

When sources conflict, higher rank wins.

## How to Use

1. Operator defines scope in a release packet.
2. Tools receive a short launch command pointing to this library.
3. Tools read the packet, execute only approved scope, update `STATUS.md` and `TOOL_LOG.md`.
4. Tools return a STEP report.
5. No tool invents scope outside the packet.

## Invariants

- Chat prompts are launch commands only — not the source of truth.
- The repo is the source of truth.
- `AGENTS.md` governs all tools; this library supplements it.
