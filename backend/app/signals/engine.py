# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Signal generation orchestrator."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from time import perf_counter
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from app.core.market.stock_models import StockSnapshot

if TYPE_CHECKING:
    from app.core.options.options_availability import OptionsAvailabilityRecorder
from app.data.options_chain_provider import OptionsChainProvider
from app.signals.adapters.theta_options_adapter import normalize_theta_chain
from app.signals.cc import generate_cc_candidates
from app.signals.csp import generate_csp_candidates
from app.signals.iron_condor import IronCondorCandidate, generate_iron_condor_candidates
from app.signals.utils import calc_dte
from app.signals.scoring import ScoredSignalCandidate, score_signals
from app.signals.selection import SelectedSignal, select_signals
from app.signals.explain import SignalExplanation, build_explanations
from app.signals.decision_snapshot import DecisionSnapshot, build_decision_snapshot
from app.signals.models import (
    CCConfig,
    CSPConfig,
    ExclusionReason,
    SignalCandidate,
    SignalEngineConfig,
)


@dataclass(frozen=True)
class SignalRunResult:
    """Result of a signal engine run."""

    as_of: datetime
    universe_id_or_hash: str
    configs: Dict[str, Any]
    candidates: List[SignalCandidate] = field(default_factory=list)
    exclusions: List[ExclusionReason] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    # Optional scored/ ranked candidates (Phase 4A). None when scoring disabled.
    scored_candidates: List[ScoredSignalCandidate] | None = None
    # Optional selected signals after applying selection policy (Phase 4A Step 2).
    selected_signals: List[SelectedSignal] | None = None
    # Optional explanations for selected signals (Phase 4B Step 1).
    explanations: List[SignalExplanation] | None = None
    # JSON-serializable decision snapshot (Phase 4B Step 2). Always set.
    decision_snapshot: DecisionSnapshot = field(default_factory=lambda: None)  # type: ignore
    # Phase 4.2: iron condor candidates (one per symbol/expiry when valid).
    iron_condor_candidates: List[IronCondorCandidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Compute stats after initialization."""
        # This is a workaround since dataclass fields can't reference other fields
        # Stats will be computed in the factory function
        pass


SYMBOL_PROCESSING_TIMEOUT_SECONDS: float = 30.0


def run_signal_engine(
    stock_snapshots: List[StockSnapshot],
    options_chain_provider: OptionsChainProvider,
    base_config: SignalEngineConfig,
    csp_config: CSPConfig,
    cc_config: CCConfig,
    universe_id_or_hash: str = "default",
    options_availability_recorder: Optional["OptionsAvailabilityRecorder"] = None,
) -> SignalRunResult:
    """Run signal engine for a list of stock snapshots.

    Args:
        stock_snapshots: List of stock snapshots to evaluate
        options_chain_provider: Provider for fetching options chains
        base_config: Base signal engine configuration
        csp_config: CSP-specific configuration
        cc_config: CC-specific configuration
        universe_id_or_hash: Identifier for the universe used

    Returns:
        SignalRunResult with candidates, exclusions, and stats
    """
    all_candidates: List[SignalCandidate] = []
    all_exclusions: List[ExclusionReason] = []
    all_iron_condor_candidates: List[IronCondorCandidate] = []
    as_of = datetime.now()

    # Process each stock snapshot
    for snapshot in stock_snapshots:
        if not snapshot.has_options:
            continue

        symbol = snapshot.symbol.upper()
        symbol_exclusions: List[ExclusionReason] = []

        # Per-symbol timing and progress logging
        symbol_start = perf_counter()
        print(f"-> Processing symbol {symbol}", flush=True)

        # Fetch expirations for this symbol
        try:
            exp_start = perf_counter()
            print(f"  [timing] fetch_expirations start for {symbol}", flush=True)
            expirations = options_chain_provider.get_expirations(symbol)
            exp_elapsed_ms = int((perf_counter() - exp_start) * 1000)
            total_expirations = len(expirations) if expirations is not None else 0
            print(
                f"  [timing] fetch_expirations done for {symbol} in {exp_elapsed_ms} ms "
                f"(total_expirations={total_expirations})",
                flush=True,
            )
        except Exception as e:
            if options_availability_recorder:
                options_availability_recorder.record_reason(symbol, "CHAIN_FETCH_ERROR")
            symbol_exclusions.append(
                ExclusionReason(
                    code="CHAIN_FETCH_ERROR",
                    message=f"Failed to fetch expirations for {symbol}: {e}",
                    data={"symbol": symbol, "error": str(e)},
                )
            )
            all_exclusions.extend(symbol_exclusions)
            continue

        if not expirations:
            if options_availability_recorder:
                options_availability_recorder.record_reason(symbol, "NO_EXPIRATIONS")
            symbol_exclusions.append(
                ExclusionReason(
                    code="NO_EXPIRATIONS",
                    message=f"No expirations found for {symbol}",
                    data={"symbol": symbol},
                )
            )
            all_exclusions.extend(symbol_exclusions)
            continue

        # Normalize expirations to date objects and filter by DTE window
        normalized_expirations: List[date] = []
        for expiry in expirations:
            if isinstance(expiry, date):
                expiry_date = expiry
            else:
                # Try to parse from string or other date-like objects
                try:
                    # Support ISO string "YYYY-MM-DD"
                    expiry_date = date.fromisoformat(str(expiry))
                except Exception:
                    # Skip unparseable expirations
                    continue
            normalized_expirations.append(expiry_date)

        # Deduplicate and sort ascending for deterministic behavior
        if normalized_expirations:
            unique_sorted_expirations = sorted(set(normalized_expirations))
        else:
            unique_sorted_expirations = []

        # Filter by DTE window based on as_of
        dte_filtered_expirations: List[date] = []
        for expiry_date in unique_sorted_expirations:
            dte = calc_dte(as_of, expiry_date)
            if base_config.dte_min <= dte <= base_config.dte_max:
                dte_filtered_expirations.append(expiry_date)

        print(
            f"  [timing] expirations after DTE filter for {symbol}: "
            f"{len(dte_filtered_expirations)} "
            f"(window=[{base_config.dte_min}, {base_config.dte_max}] days)",
            flush=True,
        )

        if not dte_filtered_expirations:
            if options_availability_recorder:
                options_availability_recorder.record_reason(symbol, "NO_EXPIRY_IN_DTE_WINDOW")
            symbol_exclusions.append(
                ExclusionReason(
                    code="NO_EXPIRY_IN_DTE_WINDOW",
                    message=(
                        f"No expirations for {symbol} within DTE window "
                        f"[{base_config.dte_min}, {base_config.dte_max}]"
                    ),
                    data={
                        "symbol": symbol,
                        "dte_min": base_config.dte_min,
                        "dte_max": base_config.dte_max,
                        "total_expirations": total_expirations,
                    },
                )
            )
            all_exclusions.extend(symbol_exclusions)
            continue

        # Apply hard cap on number of expirations per symbol
        max_expiries = max(base_config.max_expiries_per_symbol, 0)
        if max_expiries > 0:
            capped_expirations = dte_filtered_expirations[:max_expiries]
        else:
            capped_expirations = dte_filtered_expirations

        print(
            f"  [timing] expirations processed for {symbol}: "
            f"{len(capped_expirations)} (cap={base_config.max_expiries_per_symbol})",
            flush=True,
        )

        # Fetch and normalize options chain for filtered/capped expirations
        all_normalized_quotes: List = []
        for expiry in capped_expirations:
            # Per-symbol timeout guard inside expiry loop
            symbol_elapsed_seconds = perf_counter() - symbol_start
            if symbol_elapsed_seconds > SYMBOL_PROCESSING_TIMEOUT_SECONDS:
                elapsed_ms = int(symbol_elapsed_seconds * 1000)
                symbol_exclusions.append(
                    ExclusionReason(
                        code="SYMBOL_PROCESSING_TIMEOUT",
                        message=(
                            f"Processing symbol {symbol} exceeded timeout "
                            f"while processing expirations ({elapsed_ms} ms)"
                        ),
                        data={
                            "symbol": symbol,
                            "elapsed_ms": elapsed_ms,
                            "timeout_ms": int(SYMBOL_PROCESSING_TIMEOUT_SECONDS * 1000),
                            "last_expiry": expiry.isoformat(),
                        },
                    )
                )
                print(f"[TIMEOUT] symbol {symbol} after {elapsed_ms} ms", flush=True)
                break

            # Fetch PUT chain via bulk endpoint (one API call per expiration)
            try:
                put_start = perf_counter()
                print(
                    f"  [timing] get_chain PUT start for {symbol} {expiry}",
                    flush=True,
                )
                put_chain = options_chain_provider.get_chain(symbol, expiry, "PUT")
                put_elapsed_ms = int((perf_counter() - put_start) * 1000)
                print(
                    f"  [timing] get_chain PUT done for {symbol} {expiry} in {put_elapsed_ms} ms ({len(put_chain) if put_chain else 0} contracts)",
                    flush=True,
                )
                if put_chain:
                    normalized_puts, put_exclusions = normalize_theta_chain(
                        put_chain, snapshot.snapshot_time, underlying=symbol
                    )
                    all_normalized_quotes.extend(normalized_puts)
                    # Add symbol context to exclusions
                    for excl in put_exclusions:
                        excl_data = dict(excl.data)
                        excl_data["symbol"] = symbol
                        excl_data["expiry"] = expiry.isoformat()
                        symbol_exclusions.append(
                            ExclusionReason(
                                code=excl.code,
                                message=f"{symbol}: {excl.message}",
                                data=excl_data,
                            )
                        )
            except Exception as e:
                if options_availability_recorder:
                    options_availability_recorder.record_reason(symbol, "CHAIN_FETCH_ERROR")
                print(
                    f"  [timing] get_chain PUT error for {symbol} {expiry}: {e}",
                    flush=True,
                )
                symbol_exclusions.append(
                    ExclusionReason(
                        code="CHAIN_FETCH_ERROR",
                        message=f"Failed to fetch PUT chain for {symbol} {expiry}: {e}",
                        data={
                            "symbol": symbol,
                            "expiry": expiry.isoformat(),
                            "right": "PUT",
                            "error": str(e),
                        },
                    )
                )

            # Fetch CALL chain (uses cached data from PUT fetch)
            try:
                call_start = perf_counter()
                print(
                    f"  [timing] get_chain CALL start for {symbol} {expiry}",
                    flush=True,
                )
                call_chain = options_chain_provider.get_chain(symbol, expiry, "CALL")
                call_elapsed_ms = int((perf_counter() - call_start) * 1000)
                print(
                    f"  [timing] get_chain CALL done for {symbol} {expiry} in {call_elapsed_ms} ms ({len(call_chain) if call_chain else 0} contracts)",
                    flush=True,
                )
                if call_chain:
                    normalized_calls, call_exclusions = normalize_theta_chain(
                        call_chain, snapshot.snapshot_time, underlying=symbol
                    )
                    all_normalized_quotes.extend(normalized_calls)
                    # Add symbol context to exclusions
                    for excl in call_exclusions:
                        excl_data = dict(excl.data)
                        excl_data["symbol"] = symbol
                        excl_data["expiry"] = expiry.isoformat()
                        symbol_exclusions.append(
                            ExclusionReason(
                                code=excl.code,
                                message=f"{symbol}: {excl.message}",
                                data=excl_data,
                            )
                        )
            except Exception as e:
                if options_availability_recorder:
                    options_availability_recorder.record_reason(symbol, "CHAIN_FETCH_ERROR")
                print(
                    f"  [timing] get_chain CALL error for {symbol} {expiry}: {e}",
                    flush=True,
                )
                symbol_exclusions.append(
                    ExclusionReason(
                        code="CHAIN_FETCH_ERROR",
                        message=f"Failed to fetch CALL chain for {symbol} {expiry}: {e}",
                        data={
                            "symbol": symbol,
                            "expiry": expiry.isoformat(),
                            "right": "CALL",
                            "error": str(e),
                        },
                    )
                )

        # Phase 3.2: fetch option context for symbol (expected move, IV rank, etc.)
        option_context = None
        if hasattr(options_chain_provider, "get_option_context") and callable(
            getattr(options_chain_provider, "get_option_context", None)
        ):
            try:
                option_context = options_chain_provider.get_option_context(symbol)
            except Exception:
                option_context = None

        # Generate CSP candidates
        csp_candidates, csp_exclusions = generate_csp_candidates(
            stock=snapshot,
            options=all_normalized_quotes,
            cfg=csp_config,
            base_cfg=base_config,
            option_context=option_context,
        )
        all_candidates.extend(csp_candidates)

        # Add symbol context to CSP exclusions
        for excl in csp_exclusions:
            excl_data = dict(excl.data)
            excl_data["symbol"] = symbol
            symbol_exclusions.append(
                ExclusionReason(
                    code=excl.code,
                    message=f"{symbol}: {excl.message}",
                    data=excl_data,
                )
            )

        # Generate CC candidates
        cc_candidates, cc_exclusions = generate_cc_candidates(
            stock=snapshot,
            options=all_normalized_quotes,
            cfg=cc_config,
            base_cfg=base_config,
            option_context=option_context,
        )
        all_candidates.extend(cc_candidates)

        # Add symbol context to CC exclusions
        for excl in cc_exclusions:
            excl_data = dict(excl.data)
            excl_data["symbol"] = symbol
            symbol_exclusions.append(
                ExclusionReason(
                    code=excl.code,
                    message=f"{symbol}: {excl.message}",
                    data=excl_data,
                )
            )

        # Phase 4.2: generate iron condor candidates (bull put + bear call, same expiry)
        ic_candidates, ic_exclusions = generate_iron_condor_candidates(
            stock=snapshot,
            options=all_normalized_quotes,
            base_cfg=base_config,
            option_context=option_context,
        )
        all_iron_condor_candidates.extend(ic_candidates)
        for excl in ic_exclusions:
            excl_data = dict(excl.data)
            excl_data["symbol"] = symbol
            symbol_exclusions.append(
                ExclusionReason(
                    code=excl.code,
                    message=f"{symbol}: {excl.message}",
                    data=excl_data,
                )
            )

        all_exclusions.extend(symbol_exclusions)

        # Per-symbol completion logging
        total_elapsed_ms = int((perf_counter() - symbol_start) * 1000)
        print(f"[OK] Finished symbol {symbol} in {total_elapsed_ms} ms", flush=True)

    # Sort candidates deterministically: (symbol, signal_type, expiry, strike)
    sorted_candidates = sorted(
        all_candidates,
        key=lambda c: (
            c.symbol,
            c.signal_type.value,
            c.expiry,
            c.strike,
        ),
    )

    # Compute stats
    stats = {
        "total_symbols": len(stock_snapshots),
        "symbols_evaluated": len([s for s in stock_snapshots if s.has_options]),
        "total_candidates": len(sorted_candidates),
        "csp_candidates": len([c for c in sorted_candidates if c.signal_type.value == "CSP"]),
        "cc_candidates": len([c for c in sorted_candidates if c.signal_type.value == "CC"]),
        "total_exclusions": len(all_exclusions),
        "unique_exclusion_codes": len(set(e.code for e in all_exclusions)),
    }

    # Prepare configs dict
    configs_dict = {
        "base": {
            "dte_min": base_config.dte_min,
            "dte_max": base_config.dte_max,
            "min_bid": base_config.min_bid,
            "min_open_interest": base_config.min_open_interest,
            "max_spread_pct": base_config.max_spread_pct,
        },
        "csp": {
            "delta_min": csp_config.delta_min,
            "delta_max": csp_config.delta_max,
            "prob_otm_min": csp_config.prob_otm_min,
        },
        "cc": {
            "delta_min": cc_config.delta_min,
            "delta_max": cc_config.delta_max,
            "prob_otm_min": cc_config.prob_otm_min,
        },
    }

    # Optional scoring (Phase 4A) - does not affect raw candidates or stats
    scored_candidates: List[ScoredSignalCandidate] | None = None
    if base_config.scoring_config is not None and sorted_candidates:
        scored_candidates = score_signals(
            candidates=sorted_candidates,
            config=base_config.scoring_config,
        )

    # Optional selection (Phase 4A Step 2) - only if scoring AND selection enabled
    # Phase 2.4: select_signals returns (selected, confidence_exclusions); merge exclusions
    selected_signals: List[SelectedSignal] | None = None
    if scored_candidates is not None and base_config.selection_config is not None:
        selected_signals, confidence_exclusions = select_signals(
            scored_candidates=scored_candidates,
            config=base_config.selection_config,
        )
        if confidence_exclusions:
            all_exclusions = list(all_exclusions) + list(confidence_exclusions)

    # Optional explanations (Phase 4B Step 1) - only if selection produced results
    explanations: List[SignalExplanation] | None = None
    if selected_signals is not None and base_config.selection_config is not None:
        explanations = build_explanations(
            selected_signals=selected_signals,
            selection_config=base_config.selection_config,
        )

    # Build result first (without snapshot)
    result = SignalRunResult(
        as_of=as_of,
        universe_id_or_hash=universe_id_or_hash,
        configs=configs_dict,
        candidates=sorted_candidates,
        exclusions=all_exclusions,
        stats=stats,
        scored_candidates=scored_candidates,
        selected_signals=selected_signals,
        explanations=explanations,
        decision_snapshot=None,  # Placeholder, will be replaced
        iron_condor_candidates=all_iron_condor_candidates,
    )

    # Build JSON-serializable decision snapshot (Phase 4B Step 2)
    options_diagnostics = None
    if options_availability_recorder:
        options_diagnostics = {
            "symbols_with_options": options_availability_recorder.get_symbols_with_options(),
            "symbols_without_options": options_availability_recorder.get_symbols_without_options(),
        }
    decision_snapshot = build_decision_snapshot(result, options_diagnostics=options_diagnostics)

    # Return result with snapshot attached (reconstruct to set decision_snapshot)
    return SignalRunResult(
        as_of=result.as_of,
        universe_id_or_hash=result.universe_id_or_hash,
        configs=result.configs,
        candidates=result.candidates,
        exclusions=result.exclusions,
        stats=result.stats,
        scored_candidates=result.scored_candidates,
        selected_signals=result.selected_signals,
        explanations=result.explanations,
        decision_snapshot=decision_snapshot,
        iron_condor_candidates=result.iron_condor_candidates,
    )


__all__ = ["SignalRunResult", "run_signal_engine"]
