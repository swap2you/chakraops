# Secrets and Environment Policy

This document formalizes secret handling so it never regresses. All contributors and automation must follow it.

---

## Policy Statements

### 1. `.env` is never committed

- Files named `.env` or matching `*.env` (where they contain secrets) **must not** be committed to the repository.
- Both the repository root and the `chakraops` directory have `.gitignore` entries that explicitly exclude `.env`.
- **GitHub push protection** (e.g. branch protection or secret scanning that blocks commits containing secrets) is **intentional** and **must not be bypassed**. Do not add instructions to disable or work around such protection.

### 2. Tests must never require real secrets

- **Unit and regression tests** must not depend on real API keys, tokens, or webhooks (ORATS, Slack, broker, etc.).
- Tests use mocks, fixtures, or patched clients. Missing `ORATS_API_KEY` (or similar) must not cause unit test failures.
- Optional integration or smoke tests that use credentials may rely only on **environment injection** (e.g. CI secrets, local `.env` not in repo). They must be clearly separated and skippable when secrets are not present.

### 3. Regression may rely on secrets only via environment

- If any part of the regression pipeline ever uses secrets (e.g. for a limited integration run), those secrets must be **injected via environment** (e.g. CI secret variables), not hardcoded or committed.
- The default regression run (e.g. `pytest chakraops/tests/`) must pass with **no** secrets set.

### 4. Example and documentation only

- `.env.example` (or equivalent) files document **variable names and purpose**, not real values. They may contain placeholders like `your_orats_token_here` or be empty. Never commit real secrets in example files.

---

## Repository and .gitignore

- **Root** (ChakraOps): `.gitignore` MUST include `.env` and `*.env` (or equivalent) so that env files containing secrets are not committed.
- **chakraops**: `.gitignore` MUST include `.env` and `*.env` for the same reason.

If you add new secret-bearing files or patterns, add them to `.gitignore` and document them here.

---

## .env.example

- **chakraops**: A `.env.example` exists and lists the environment variables used by the backend (e.g. ORATS, Slack, API key). Copy to `.env` locally and fill in values; `.env` is ignored by git.
- **frontend**: A `.env.example` exists for frontend-specific variables (e.g. API base URL, API key). Same rule: copy to `.env` locally; do not commit `.env`.

Do not add GitHub policy bypass instructions. Push protection and secret scanning are there to prevent accidental commit of secrets.
