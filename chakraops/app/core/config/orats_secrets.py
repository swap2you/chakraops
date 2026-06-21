# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS API token resolution — environment only.

No token value is stored in source. The token is read from the
``ORATS_API_TOKEN`` environment variable (``ORATS_API_KEY`` is accepted as an
alias). Configure it locally via a gitignored ``.env`` (see ``.env.example``).

``ORATS_API_TOKEN`` remains exposed as a module attribute for backward
compatibility with existing importers and test patches
(``patch("app.core.config.orats_secrets.ORATS_API_TOKEN", ...)``). Its value is
resolved from the environment at import time and is ``None`` when unset, so a
missing credential fails loudly downstream rather than silently degrading.
"""
import os


def _read_token_from_env() -> str | None:
    return (os.environ.get("ORATS_API_TOKEN") or os.environ.get("ORATS_API_KEY") or "").strip() or None


# Backward-compatible module-level constant (env-resolved; never hardcoded).
ORATS_API_TOKEN = _read_token_from_env()


def get_orats_token(required: bool = False) -> str | None:
    """Return the ORATS token from the environment, re-read on each call.

    When ``required`` is True, raise a clear error if the token is missing so
    callers fail loudly instead of silently falling back to no/alternate data.
    Never logs or returns the token value in error messages.
    """
    token = _read_token_from_env()
    if required and not token:
        raise RuntimeError(
            "ORATS_API_TOKEN is not set. Configure it in the environment "
            "(see chakraops/.env.example). No hardcoded token is provided and "
            "no fallback data source is used."
        )
    return token
