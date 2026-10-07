# CLAUDE.md — ChakraOps Quick Reference

Read `AGENTS.md` first. This file is a thin Claude-specific supplement.

## Paths

- Final checkout: `C:\Users\swap2\NEEWA-Personal\Projects\ChakraOps`
- Backend: `backend/`
- Frontend: `frontend/`
- Strategy config: `backend/config/`
- Operating commands: `docs/OPERATIONS.md`

## Commands

```bash
# From the repository root
powershell -NoProfile -File .\chakra.ps1 test
powershell -NoProfile -File .\chakra.ps1 status
```

## Stop Conditions

- Ambiguous scope
- Failed gate
- Conflict with `AGENTS.md`
- Operator denial
- Cursor actively editing the same release
