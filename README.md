# ChakraOps

Manual options and shares decision support for a wheel-style workflow. ChakraOps recommends; the operator places trades. Broker order routing stays off.

Canonical checkout: `C:\Users\swap2\NEEWA-Personal\projects\ChakraOps`.

Origin: `https://github.com/swap2you/chakraops.git`, branch `main`.

## Commands

From the repository root:

```text
powershell -NoProfile -File .\chakra.ps1 setup
powershell -NoProfile -File .\chakra.ps1 start
powershell -NoProfile -File .\chakra.ps1 stop
powershell -NoProfile -File .\chakra.ps1 test
powershell -NoProfile -File .\chakra.ps1 status
```

- Backend: http://127.0.0.1:18800
- Frontend: http://127.0.0.1:18873

Operating detail is in [docs/OPERATIONS.md](docs/OPERATIONS.md). NEEWA ownership is in [docs/NEEWA.md](docs/NEEWA.md). Agent rules are in [AGENTS.md](AGENTS.md).
