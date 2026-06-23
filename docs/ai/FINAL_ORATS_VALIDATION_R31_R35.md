# Final ORATS Validation — R31–R35

- ORATS is the sole active options-data provider across R31–R35
- C-1 (R32): environment-only token loading; no committed secrets
- R34: provider error path redaction complete
- R35: `provider_health` job probes ORATS; ops status exposes token-present boolean only
- No silent fallback provider introduced
- Backups exclude `.env`
