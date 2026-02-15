# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase UI-1: Type stubs for Run Results / Diagnostics API responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class TopRankedRow(TypedDict, total=False):
    symbol: str
    status: str
    score: Optional[int]
    band: Optional[str]
    mode: str
    strike: Optional[float]
    dte: Optional[int]
    premium: Optional[float]
    primary_reason: Optional[str]


class Throughput(TypedDict, total=False):
    wall_time_sec: float
    requests_estimated: Optional[int]
    cache_hit_rate_by_endpoint: Dict[str, Any]


class LatestRunResponse(TypedDict, total=False):
    run_id: Optional[str]
    as_of: Optional[str]
    status: str
    duration_sec: float
    symbols_evaluated: int
    symbols_skipped: int
    top_ranked: List[TopRankedRow]
    warnings: List[str]
    throughput: Throughput


class SymbolStage1(TypedDict, total=False):
    data_sufficiency: Dict[str, Any]
    data_as_of: Optional[str]
    endpoints_used: List[str]


class SymbolStage2(TypedDict, total=False):
    candidate_contract: Optional[Dict[str, Any]]
    score: Optional[int]
    band: Optional[str]
    eligibility: Dict[str, Any]
    fail_reasons: List[str]


class SymbolResponse(TypedDict, total=False):
    symbol: str
    stage1: SymbolStage1
    stage2: SymbolStage2
    sizing: Dict[str, Any]
    exit_plan: Dict[str, Any]
    traces: Dict[str, Any]
    error: Optional[str]


class SystemHealthResponse(TypedDict, total=False):
    run_id: Optional[str]
    as_of: Optional[str]
    watchdog: Dict[str, Any]
    cache: Dict[str, Any]
    budget: Dict[str, Any]
    recent_run_ids: List[str]
