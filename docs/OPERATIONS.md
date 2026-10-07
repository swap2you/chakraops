# ChakraOps operations

Canonical checkout: `C:\Users\swap2\NEEWA-Personal\projects\ChakraOps`.

One command surface, from the repository root:

```text
powershell -NoProfile -File .\chakra.ps1 setup
powershell -NoProfile -File .\chakra.ps1 start
powershell -NoProfile -File .\chakra.ps1 stop
powershell -NoProfile -File .\chakra.ps1 test
powershell -NoProfile -File .\chakra.ps1 status
```

- Backend listens on http://127.0.0.1:18800
- Frontend listens on http://127.0.0.1:18873
- Python package and strategy config: `backend/` and `backend/config/`
- Interpreter: `backend\.venv\Scripts\python.exe`
- Direct dependencies: `backend/requirements.txt` (pinned)
- Frontend lock: `frontend/package-lock.json`
- Local data, logs, and the review packet stay out of Git (`runtime/`, `out/`, `data/`, `deliverables/`)
- Trading is manual. Broker writes stay off.
- `status` reports scheduled tasks and workflow schedule keys that are actually present. It does not claim a schedule is disabled unless that observation is empty.

`setup` creates `runtime/`, `00_inbox/`, `deliverables/`, and an empty `99_archive/`. A failed `python`, `pip`, or `npm` command exits nonzero and does not print the setup completion line.

## Troubleshooting

| Observation | What to do |
| --- | --- |
| `status` says a URL is down | Run `start`. If the port is already taken by this checkout, run `stop` first. |
| `stop` keeps the ownership record | An owned listener on 18800 or 18873 was still running. Inspect that PID. Do not kill an unrelated listener. |
| `venv missing` | Run `setup`. Python 3.13 is the version CI and this checkout use. |
| Frontend proxy fails | Backend health is `http://127.0.0.1:18800/api/healthz`. The UI proxies `/api` to that port. |
| ORATS reads fail | Credentials stay in local `backend/.env`. Do not print them. There is no silent provider fallback. |
| A GitHub workflow shows a schedule | Recurring cron is not authorized. `market-health.yml` is manual `workflow_dispatch` only. Push and pull-request CI in `ci.yml` stays. |

## Dependency compatibility (reviewed 2026-10-07)

Python 3.13.15 and the pinned backend set import in this checkout. FastAPI 0.142.2 was the newest release on the package index at review time and is already installed.

These frontend majors were not upgraded, because doing so would replace the UI framework rather than bump a compatible dependency:

| Package | Locked line | Newest observed | Exception |
| --- | --- | --- | --- |
| react / react-dom | 18.2.x via `package-lock.json` | 19.3.0 | Testing Library 14 and the current Vite 5 plugin target React 18. |
| vite | 5.0.x | 8.3.3 | Vite 8 is a new major with a different config and plugin contract. |
| typescript | 5.3.x | 7.0.2 | TypeScript 7 would be a compiler migration across the existing UI. |

`frontend/package-lock.json` is the reproducible frontend definition. `backend/requirements.txt` pins the direct Python packages verified here.
