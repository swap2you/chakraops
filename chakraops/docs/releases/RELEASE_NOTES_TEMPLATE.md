# Release RXX.Y — [Short title]

**Date:** YYYY-MM  
**Goal:** [One sentence: what this release achieves.]

---

## Scope

- **In scope:** [Bullet list of what is included.]
- **Out of scope:** [Bullet list of what is explicitly not included; e.g. "Decision JSON schema unchanged.", "No new persistence for X."]

---

## API changes (if any)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST/... | `/api/...` | [Brief description.] |

Example response shape (short; do not paste giant payloads):

```json
{ "key": "value", "optional_field": "..." }
```

---

## UI changes (if any)

- [Bullet list: pages/sections changed, new components, copy changes.]

---

## Data / persistence (if any)

- [e.g. "No changes to decision_latest.json." / "New file out/foo.json with retention policy."]

---

## Tests

- **Backend:** [Test file(s) and what they cover.]
- **Frontend:** [Test file(s) and what they cover.]

---

## Verification and UAT

- **Commands run:**  
  - Backend: `cd chakraops && python -m pytest <path> -v --tb=short`  
  - Frontend: `cd frontend && npm run test -- --run <path>`  
  - Build gate: `cd frontend && npm run build`
- **UAT evidence path:** `out/verification/RXX.Y/notes.md` (and `api_samples/` if applicable).
- **Manual steps:** [Short list of what was verified by hand.]

---

## Known issues (if any)

- [List or "None."]

---

## Rollback notes

- [e.g. "Revert commit X; no DB migration." / "If rollback, clear out/foo.json."]

---

## File list (summary)

- [Key files added/changed; not exhaustive.]
