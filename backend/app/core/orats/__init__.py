"""
ORATS API clients.

Live endpoints (orats_client):
  - GET /datav2/live/strikes
  - GET /datav2/live/summaries

Delayed Data API / OPRA enrichment (orats_opra):
  - GET /datav2/strikes (param: ticker)
  - GET /datav2/strikes/options (param: tickers - PLURAL)
"""
from app.core.orats.orats_client import (
    OratsUnavailableError,
    probe_orats_live,
    get_orats_live_strikes,
    get_orats_live_summaries,
)

from app.core.orats.orats_opra import (
    # Symbol helpers
    to_yymmdd,
    build_orats_option_symbol,
    validate_orats_option_symbol,
    parse_orats_option_symbol,
    # Client
    OratsDelayedClient,
    OratsDelayedError,
    # Data classes
    OptionContract,
    UnderlyingQuote,
    OpraEnrichmentResult,
    # High-level functions
    fetch_opra_enrichment,
    check_opra_liquidity_gate,
)

__all__ = [
    # Live client
    "OratsUnavailableError",
    "probe_orats_live",
    "get_orats_live_strikes",
    "get_orats_live_summaries",
    # Delayed/OPRA client
    "to_yymmdd",
    "build_orats_option_symbol",
    "validate_orats_option_symbol",
    "parse_orats_option_symbol",
    "OratsDelayedClient",
    "OratsDelayedError",
    "OptionContract",
    "UnderlyingQuote",
    "OpraEnrichmentResult",
    "fetch_opra_enrichment",
    "check_opra_liquidity_gate",
]
