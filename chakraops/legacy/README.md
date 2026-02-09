# Legacy — reference only

This directory contains **legacy artifacts and scripts** that are **not used by the current evaluation pipeline**. They are kept for reference only.

- **Not used by the current pipeline:** The evaluation pipeline is ORATS-based (staged evaluator, ORATS chain provider). These modules are not on that path.
- **Not exercised by tests or runtime:** CI and main application flow do not depend on code in this directory.
- **Kept for reference:** ThetaTerminal JAR, ThetaData smoke/debug scripts, and similar artifacts may be useful for historical context or local experimentation with ThetaData/ThetaTerminal. Do not rely on them for operation.

**Contents:**

- `thedata/` — ThetaTerminal v3 JAR and lib (optional local server for ThetaTerminal HTTP API). Not required for ORATS-based evaluation.
- `scripts/` — Theta-specific smoke and debug scripts (e.g. ThetaData v3 smoketest, Theta SPY expirations). Not run by CI or the main app.

Some Theta-related code (e.g. ThetaTerminal HTTP provider, ThetaData provider, theta options adapter) remains in `app/` for optional live UI / shadow use. The **authoritative evaluation path** uses ORATS only.
