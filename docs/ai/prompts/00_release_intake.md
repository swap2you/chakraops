# Prompt 00 — Release Intake

**Phase:** START RELEASE  
**Used by:** Operator / ChatGPT / Cursor

---

## Instructions

Read this file before creating or initializing a release.

1. Read `AGENTS.md`.
2. Read `docs/ai/README.md` and `docs/ai/OPERATING_MODEL.md`.
3. Read `docs/ai/RELEASE_TRAVELER.md` to confirm `<Release>` is the next planned release.
4. Confirm branch `release/<Release>` exists and is checked out.
5. Confirm `git status --short` is clean.
6. Confirm `docs/ai/releases/<Release>/RELEASE_PACKET.md` exists.
7. Read `docs/ai/releases/<Release>/RELEASE_PACKET.md` in full.
8. Initialize or verify `docs/ai/releases/<Release>/STATUS.md`.
9. Initialize or verify `docs/ai/releases/<Release>/TOOL_LOG.md`.
10. Return a summary: release, objective, risk level, allowed files, forbidden files, gates required, review requirements.

**Do not implement. Do not commit. Do not push.**

---

## Template Values

| Placeholder | Meaning |
|-------------|---------|
| `<Release>` | Release identifier, e.g. `R31.0` |
| `<Branch>` | Git branch, e.g. `release/R31.0` |
| `<Objective>` | One-sentence release goal |
| `<Risk level>` | Level 0–4 per `docs/ai/REVIEW_POLICY.md` |
| `<Allowed files>` | Comma-separated list of files/paths allowed to change |
| `<Forbidden files>` | Files that must not change |
| `<Gates>` | Required verification gates |
| `<Review level>` | Tools required to review |

---

## Stop Conditions

- Branch does not exist → STOP, report to operator
- RELEASE_PACKET.md does not exist → STOP, request operator to create it
- Working tree dirty → STOP, report unexpected changes
