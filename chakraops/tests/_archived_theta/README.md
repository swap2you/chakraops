# Archived Theta tests

These tests reference the Theta provider / ThetaTerminal and are **excluded from pytest** via `pytest.ini` (`norecursedirs` includes `_archived_theta`).

- **test_theta_options_adapter.py** — normalize_theta_chain, NormalizedOptionQuote; uses fixtures/theta_chain_sample.json
- **test_provider_selection.py** — ThetaTerminal vs yfinance vs SnapshotOnly selection
- **test_thetadata_provider.py** — ThetaData provider (legacy, was in tests/legacy/)

Kept for reference; not run in CI or `pytest -q`.
