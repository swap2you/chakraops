# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.6: Canonical DecisionArtifactV2 schema — ONE pipeline, ONE artifact, ONE store."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

# Band mapping: centralized logic. NEVER null — D for lowest.
try:
    from app.core.scoring.config import TIER_A_MIN, TIER_B_MIN, TIER_C_MIN
except Exception:
    TIER_A_MIN, TIER_B_MIN, TIER_C_MIN = 80, 60, 40


def normalize_contract_key(strike: Optional[float], expiry: Optional[str], option_type: str) -> Optional[str]:
    """R23.1: Canonical contract_key format: {strike_int}-{expiry}-PUT|CALL. Strike as int (no trailing .0)."""
    if strike is None or not expiry:
        return None
    try:
        s = float(strike)
        strike_int = int(round(s))
    except (TypeError, ValueError):
        return None
    exp_str = str(expiry).strip()[:10]
    if not exp_str:
        return None
    opt = (option_type or "PUT").upper()
    if opt not in ("PUT", "CALL"):
        opt = "PUT"
    return f"{strike_int}-{exp_str}-{opt}"


def assign_band(score: Optional[int | float]) -> str:
    """Centralized band assignment. NEVER null — returns A|B|C|D."""
    if score is None:
        return "D"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "D"
    if s >= TIER_A_MIN:
        return "A"
    if s >= TIER_B_MIN:
        return "B"
    if s >= TIER_C_MIN:
        return "C"
    return "D"  # Below C — always D, never null


def assign_band_reason(score: Optional[int | float]) -> str:
    """Band reason from score thresholds only. NEVER mentions verdict (verdict is separate)."""
    b = assign_band(score)
    if score is None:
        return f"Band {b} because score is None/invalid (default)"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return f"Band {b} because score is invalid (default)"
    if b == "A":
        return f"Band {b} because score >= {TIER_A_MIN}"
    if b == "B":
        return f"Band {b} because score >= {TIER_B_MIN} and < {TIER_A_MIN}"
    if b == "C":
        return f"Band {b} because score >= {TIER_C_MIN} and < {TIER_B_MIN}"
    return f"Band {b} because score < {TIER_C_MIN}"


# R22.7: Strict machine code format — only ^[A-Z0-9_]+$ allowed in persisted primary_reason_codes
_STRICT_CODE_RE = re.compile(r"^[A-Z0-9_]+$")

# R23.2: Gate name <-> gate_code mapping (code-only persistence; UI labels at request time)
_GATE_NAME_TO_CODE: Dict[str, str] = {
    "Stock Quality (Stage 1)": "STOCK_QUALITY_STAGE1",
    "Stage 1": "STOCK_QUALITY_STAGE1",
    "Stage1": "STOCK_QUALITY_STAGE1",
    "Options Liquidity (Stage 2)": "OPTIONS_LIQUIDITY_STAGE2",
    "Options Liquidity": "OPTIONS_LIQUIDITY_STAGE2",
    "Stage 2": "OPTIONS_LIQUIDITY_STAGE2",
    "Stage2": "OPTIONS_LIQUIDITY_STAGE2",
    "Delta band": "DELTA_BAND",
    "DeltaBand": "DELTA_BAND",
    "ORATS Summary": "ORATS_SUMMARY",
    "Earnings Check": "EARNINGS_CHECK",
}
_GATE_CODE_TO_LABEL: Dict[str, str] = {
    "STOCK_QUALITY_STAGE1": "Stock quality (Stage 1)",
    "OPTIONS_LIQUIDITY_STAGE2": "Options liquidity (Stage 2)",
    "DELTA_BAND": "Delta band",
    "ORATS_SUMMARY": "ORATS summary",
    "EARNINGS_CHECK": "Earnings check",
}


def gate_name_to_code(name: Optional[str]) -> str:
    """R23.2: Map UI gate name to persisted code. Returns UNKNOWN_GATE if no match or invalid."""
    if not name or not isinstance(name, str):
        return "UNKNOWN_GATE"
    n = name.strip()
    if _STRICT_CODE_RE.match(n):
        return n
    return _GATE_NAME_TO_CODE.get(n, _GATE_NAME_TO_CODE.get(n.replace(" ", ""), "UNKNOWN_GATE"))


def gate_code_to_label(code: Optional[str]) -> str:
    """R23.2: Map persisted gate_code to safe UI label (request-time only)."""
    if not code or not isinstance(code, str):
        return "Gate"
    return _GATE_CODE_TO_LABEL.get(code.strip(), code.replace("_", " ").title())

def _reason_string_to_codes(reason: Optional[str]) -> List[str]:
    """R22.7: Convert primary_reason string to strict machine codes (no prose)."""
    codes, _ = _reason_string_to_codes_and_count(reason)
    return codes


def _reason_string_to_codes_and_count(reason: Optional[str]) -> tuple[List[str], Optional[int]]:
    """R22.7: Normalize reason to strict codes + optional rejected_due_to_delta count. No prose."""
    if not reason or not isinstance(reason, str):
        return [], None
    reason = reason.strip()
    rejected_count: Optional[int] = None

    # Prose -> single code mappings (no parentheses, colons, equals in output)
    if "Stock qualified" in reason or reason.startswith("Stock qualified"):
        return ["STOCK_QUALIFIED"], None
    if "Chain evaluated" in reason or "contract selected" in reason.lower():
        return ["CHAIN_SELECTED"], None
    if "Options liquidity confirmed" in reason or "OPRA" in reason:
        return ["OPTIONS_LIQUIDITY_OPRA"], None
    if "Chain evaluation error" in reason:
        return ["CHAIN_EVALUATION_ERROR"], None
    if "OPTION_CHAIN_MISSING_FIELDS" in reason:
        return ["OPTION_CHAIN_MISSING_FIELDS"], None
    if "Stock qualified, chain pending" in reason:
        return ["STOCK_QUALIFIED_CHAIN_PENDING"], None
    if "Stage 2 skipped" in reason:
        return ["STAGE2_SKIPPED"], None
    if "Blocked by market regime" in reason or "RISK_OFF" in reason:
        return ["REGIME_RISK_OFF"], None
    if "Not evaluated" in reason:
        return ["NOT_EVALUATED"], None
    if "Evaluation error" in reason:
        return ["EVALUATION_ERROR"], None

    # rejected_due_to_delta=N -> code + count
    match = re.search(r"rejected_due_to_delta\s*=\s*(\d+)", reason, re.IGNORECASE)
    if match:
        try:
            rejected_count = int(match.group(1))
        except (ValueError, TypeError):
            pass
        return ["REJECTED_DUE_TO_DELTA"], rejected_count

    # FAIL_* / WARN_* -> strip prefix and keep only if strict
    codes: List[str] = []
    for part in reason.split(";"):
        part = part.strip()
        if not part:
            continue
        if part.startswith("FAIL_"):
            c = part[5:]
            if _STRICT_CODE_RE.match(c):
                codes.append(c)
        elif part.startswith("WARN_"):
            c = part[5:]
            if _STRICT_CODE_RE.match(c):
                codes.append(c)
        elif _STRICT_CODE_RE.match(part):
            codes.append(part)
    return codes, rejected_count


def _rank_reason_prose_to_codes(reasons: Optional[List[Any]]) -> List[str]:
    """R22.7 Fix Pack: Map rank_reasons.reasons (prose) to rank_reason_codes. No prose in persisted artifact."""
    if not reasons:
        return []
    codes: List[str] = []
    for r in reasons:
        s = (r or "").strip()
        if not s or not _STRICT_CODE_RE.match(s):
            if "Regime RISK_ON" in s or s == "Regime RISK_ON":
                codes.append("REGIME_RISK_ON")
            elif "Regime NEUTRAL" in s or s == "Regime NEUTRAL":
                codes.append("REGIME_NEUTRAL")
            elif "IV Rank HIGH" in s or "favorable premium" in s.lower():
                codes.append("IVR_HIGH_FAVORABLE")
            elif "High data completeness" in s:
                codes.append("HIGH_DATA_COMPLETENESS")
            elif "Acceptable data completeness" in s:
                codes.append("ACCEPTABLE_DATA_COMPLETENESS")
            elif "Options liquidity passed" in s or "liquidity passed" in s.lower():
                codes.append("OPTIONS_LIQUIDITY_PASSED")
            elif "Eligible for trade" in s:
                codes.append("ELIGIBLE_FOR_TRADE")
            elif "Capital efficient" in s:
                codes.append("CAPITAL_EFFICIENT")
            elif "Low notional" in s or "notional %" in s.lower():
                codes.append("LOW_NOTIONAL_PCT")
            else:
                codes.append("RANK_REASON")
        else:
            codes.append(s)
    return codes[:5]


def _exit_plan_reason_to_code(reason: Optional[str]) -> str:
    """R22.7 Fix Pack: Map exit_plan.reason (prose) to reason_code. No prose in persisted artifact."""
    if not reason or not isinstance(reason, str):
        return "EXITPLAN_AVAILABLE"
    r = reason.strip()
    if "not computed" in r.lower() or "Missing inputs" in r:
        return "EXITPLAN_MISSING_INPUTS"
    if "error" in r.lower():
        return "EXITPLAN_ERROR"
    return "EXITPLAN_NOT_AVAILABLE"


# R25.7: Safe earnings status set for persistence (never persist EARNINGS_NOT_EVALUATED or raw FAIL_/WARN_)
_EARNINGS_PERSIST_SAFE_STATUS = frozenset({"OK", "Unavailable", "Stale", "EARNINGS_BLOCKED"})


def _earnings_note_to_status_code(note: Optional[str], earnings_block: Optional[bool], earnings_days: Optional[int]) -> str:
    """R22.7 Fix Pack: Persist status_code only; never prose note. R25.7: Never return EARNINGS_NOT_EVALUATED for persist."""
    if earnings_block:
        return "EARNINGS_BLOCKED"
    if earnings_days is not None:
        return "EARNINGS_OK"
    if (note or "").strip().lower() in ("not evaluated", "not evaluated.", ""):
        return "Unavailable"  # R25.7: Never persist EARNINGS_NOT_EVALUATED
    return "EARNINGS_STATUS"


def _band_rank_value(band: str) -> int:
    """Numeric value for band ordering (A > B > C > D). Phase 8.0."""
    return {"A": 4, "B": 3, "C": 2, "D": 1}.get((band or "D").upper(), 1)


def compute_rank_score(
    band: str,
    score: Optional[float],
    premium_yield_pct: Optional[float],
    capital_required: Optional[float],
    market_cap: Optional[float],
) -> float:
    """
    Phase 8.0: Sortable rank_score.
    Primary: band (A>B>C>D), Secondary: score desc, Tertiary: premium_yield desc,
    Quaternary: capital_required asc, Tie-breaker: market_cap desc.
    """
    band_val = _band_rank_value(band) * 100_000
    score_val = (score if score is not None else 0) * 100
    yield_val = (premium_yield_pct if premium_yield_pct is not None else 0) * 10
    cap_val = -(capital_required or 999_999) / 100  # lower capital = higher rank
    mcap_val = (market_cap or 0) / 1e9
    return band_val + score_val + yield_val + cap_val + mcap_val


@dataclass
class SymbolEvalSummary:
    """One row per universe symbol. All fields explicit (no optional blanks)."""
    symbol: str
    verdict: str  # ELIGIBLE|HOLD|BLOCKED|NOT_EVALUATED
    final_verdict: str
    score: Optional[int | float]
    band: str  # A|B|C|D — never null
    primary_reason: Optional[str]
    stage_status: str  # RUN|NOT_RUN
    stage1_status: str  # PASS|FAIL|NOT_RUN
    stage2_status: str  # PASS|FAIL|NOT_RUN
    provider_status: Optional[str]  # OK|WARN|ERROR
    data_freshness: Optional[str]  # ISO
    evaluated_at: Optional[str]   # ISO
    strategy: Optional[str]  # CSP|CC|STOCK
    price: Optional[float]
    expiration: Optional[str]  # ISO or YYYY-MM-DD
    has_candidates: bool
    candidate_count: int
    # Phase 7.7 / 10.1: Trust + score clarity
    score_breakdown: Optional[Dict[str, Any]] = None  # stage1_score, stage2_score, raw_score, final_score, score_caps, regime_score
    raw_score: Optional[int | float] = None  # composite before any cap (0-100)
    pre_cap_score: Optional[int | float] = None  # same as raw_score; alias for display
    final_score: Optional[int | float] = None  # after caps; band is derived from this only
    score_caps: Optional[Dict[str, Any]] = None  # { regime_cap, applied_caps: [{type, cap_value, before, after, reason}] }
    band_reason: Optional[str] = None  # "Band A because score >= TIER_A_MIN"
    max_loss: Optional[float] = None  # capital required for selected candidate
    underlying_price: Optional[float] = None  # spot at evaluation
    # Phase 8.0: Ranking fields
    capital_required: Optional[float] = None  # underlying_price * 100
    expected_credit: Optional[float] = None  # from selected candidate if eligible
    premium_yield_pct: Optional[float] = None  # expected_credit / capital_required
    market_cap: Optional[float] = None  # if available
    rank_score: Optional[float] = None  # sortable numeric score
    # R22.7: code-only persistence; no FAIL_* in persisted values
    primary_reason_codes: Optional[List[str]] = None  # e.g. ["REGIME_CONFLICT", "NO_HOLDINGS"]
    rejected_due_to_delta_count: Optional[int] = None  # when primary_reason_codes contains REJECTED_DUE_TO_DELTA

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateRow:
    """Single candidate (trade proposal) for a symbol."""
    symbol: str
    strategy: str
    expiry: Optional[str]
    strike: Optional[float]
    delta: Optional[float]
    credit_estimate: Optional[float]
    max_loss: Optional[float]
    why_this_trade: Optional[str] = None  # R22.9: optional for loader compat; never persisted
    # Phase 11.3: Exact contract identity from decision artifact (no recompute)
    contract_key: Optional[str] = None  # strike-expiry-PUT|CALL (normalized: strike as int)
    option_symbol: Optional[str] = None  # OCC symbol when available

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # R70-DEF-011: server-side return % (credit $/share ÷ strike × 100). UI must not invent this.
        if self.strike is not None and self.credit_estimate is not None and float(self.strike) > 0:
            d["expected_return_pct"] = round((float(self.credit_estimate) / float(self.strike)) * 100.0, 4)
        else:
            d["expected_return_pct"] = None
        return d


@dataclass
class GateEvaluation:
    """Gate pass/fail for Explain This Decision. R23.2: Persist gate_code only; name is for in-memory/API label."""
    name: str
    status: str  # PASS|FAIL|SKIP
    reason: Optional[str] = None  # R22.9: optional for loader compat; never persisted
    gate_code: Optional[str] = None  # R23.2: code-only persisted (e.g. STOCK_QUALITY_STAGE1)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EarningsInfo:
    """Earnings info for a symbol."""
    earnings_days: Optional[int]
    earnings_block: Optional[bool]
    note: Optional[str]  # e.g. "Not evaluated" (request-time display; not persisted)
    status_code: Optional[str] = None  # R22.7 Fix Pack: persisted code only (EARNINGS_NOT_EVALUATED, etc.)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolDiagnosticsDetails:
    """Phase 7.7: Full diagnostics per symbol for Symbol page. Persisted in v2 artifact."""
    # Technicals (from eligibility_trace / computed)
    technicals: Dict[str, Any]  # rsi, atr, atr_pct, support_level, resistance_level
    # Exit plan (T1, T2, T3, stop from build_exit_plan)
    exit_plan: Dict[str, Any]  # t1, t2, t3, stop
    # Risk flags
    risk_flags: Dict[str, Any]  # earnings_days, earnings_block, stock_liq, option_liq, data_status, missing_required
    # Phase 7.3 explanation
    explanation: Dict[str, Any]  # stock_regime_reason, support_condition, liquidity_condition, iv_condition
    # Stock snapshot (price, bid, ask, volume, etc.)
    stock: Dict[str, Any]
    # Symbol eligibility detail
    symbol_eligibility: Dict[str, Any]  # status, required_data_missing, required_data_stale, reasons
    # Liquidity detail
    liquidity: Dict[str, Any]  # stock_liquidity_ok, option_liquidity_ok, reason
    # Score breakdown and band
    score_breakdown: Optional[Dict[str, Any]] = None
    rank_reasons: Optional[Dict[str, Any]] = None
    suggested_capital_pct: Optional[float] = None
    regime: Optional[str] = None
    # Provider/options metadata
    options: Dict[str, Any] = field(default_factory=dict)  # expirations_count, contracts_count, underlying_price
    # Phase: plain-English reasons — NOT persisted; computed on-demand in API from codes + sample
    reasons_explained: Optional[List[Dict[str, Any]]] = None  # [{ code, severity, title, message, metrics }]
    # Delta rejection sample (code-only: numbers + target range); persisted so API can compute message
    sample_rejected_due_to_delta: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("reasons_explained", None)  # do not persist explanation text; compute at response time
        return d


@dataclass
class DecisionArtifactV2:
    """Canonical evaluation output. ONE schema used everywhere."""
    metadata: Dict[str, Any]  # artifact_version, mode, pipeline_timestamp, etc.
    symbols: List[SymbolEvalSummary]  # ONE ROW PER UNIVERSE SYMBOL
    selected_candidates: List[CandidateRow]  # for Dashboard A/B lists
    candidates_by_symbol: Dict[str, List[CandidateRow]] = field(default_factory=dict)
    gates_by_symbol: Dict[str, List[GateEvaluation]] = field(default_factory=dict)
    earnings_by_symbol: Dict[str, EarningsInfo] = field(default_factory=dict)
    diagnostics_by_symbol: Dict[str, SymbolDiagnosticsDetails] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "metadata": self.metadata,
            "symbols": [s.to_dict() for s in self.symbols],
            "selected_candidates": [c.to_dict() for c in self.selected_candidates],
            "candidates_by_symbol": {
                k: [c.to_dict() for c in v]
                for k, v in self.candidates_by_symbol.items()
            },
            "gates_by_symbol": {
                k: [g.to_dict() for g in v]
                for k, v in self.gates_by_symbol.items()
            },
            "earnings_by_symbol": {
                k: v.to_dict() for k, v in self.earnings_by_symbol.items()
            },
            "diagnostics_by_symbol": {
                k: v.to_dict() for k, v in self.diagnostics_by_symbol.items()
            },
            "warnings": self.warnings,
        }
        return out

    def to_dict_persist(self) -> Dict[str, Any]:
        """R22.7: Persist code-only; no prose, no FAIL_*/WARN_* in values. Strict code regex only."""

        def symbol_persist(s: SymbolEvalSummary) -> Dict[str, Any]:
            d = asdict(s)
            d.pop("primary_reason", None)
            d.pop("band_reason", None)
            codes = d.get("primary_reason_codes")
            rj_count = d.get("rejected_due_to_delta_count")
            if not codes:
                codes, rj_count = _reason_string_to_codes_and_count(getattr(s, "primary_reason", None))
            codes = [c for c in (codes or []) if _STRICT_CODE_RE.match(str(c))]
            d["primary_reason_codes"] = codes if codes else []
            if "REJECTED_DUE_TO_DELTA" in codes and rj_count is not None:
                d["rejected_due_to_delta_count"] = rj_count
            else:
                d.pop("rejected_due_to_delta_count", None)
            # R22.9: applied_caps code-only (reason_code only, no reason) in score_breakdown / score_caps
            def _sanitize_applied_caps(obj: Any) -> None:
                if isinstance(obj, dict):
                    if "applied_caps" in obj and isinstance(obj["applied_caps"], list):
                        clean = []
                        for cap in obj["applied_caps"]:
                            c = dict(cap) if isinstance(cap, dict) else {}
                            c.pop("reason", None)
                            rc = c.get("reason_code")
                            if not rc or not _STRICT_CODE_RE.match(str(rc)):
                                c["reason_code"] = "REGIME_CAP"
                            clean.append({k: v for k, v in c.items() if k in ("type", "cap_value", "before", "after", "reason_code")})
                        obj["applied_caps"] = clean
                    for v in obj.values():
                        _sanitize_applied_caps(v)
                elif isinstance(obj, list):
                    for x in obj:
                        _sanitize_applied_caps(x)
            _sanitize_applied_caps(d.get("score_breakdown"))
            _sanitize_applied_caps(d.get("score_caps"))
            return d

        def candidate_persist(c: CandidateRow) -> Dict[str, Any]:
            d = asdict(c)
            d.pop("why_this_trade", None)
            strategy_upper = (d.get("strategy") or "").upper()
            if strategy_upper in ("CSP", "CC"):
                strike, expiry = d.get("strike"), d.get("expiry") or getattr(c, "expiry", None)
                opt_type = "PUT" if strategy_upper == "CSP" else "CALL"
                nkey = normalize_contract_key(strike, expiry, opt_type)
                if nkey:
                    d["contract_key"] = d.get("contract_key") or nkey
                if not d.get("option_symbol") and getattr(c, "option_symbol", None):
                    d["option_symbol"] = c.option_symbol
            return d

        def gate_persist(g: GateEvaluation) -> Dict[str, Any]:
            # R23.2: Persist only gate_code + status (code-only; no name, no reason)
            code = (g.gate_code or gate_name_to_code(g.name)).strip()
            if not _STRICT_CODE_RE.match(code):
                code = "UNKNOWN_GATE"
            return {"gate_code": code, "status": g.status}

        def earnings_persist(e: EarningsInfo) -> Dict[str, Any]:
            """R22.7 Fix Pack: Persist status_code only; never prose note. R25.7: Never persist EARNINGS_NOT_EVALUATED."""
            d = asdict(e)
            d.pop("note", None)
            existing = (getattr(e, "status_code", None) or "").strip()
            if existing == "EARNINGS_NOT_EVALUATED":
                status = "Unavailable"
            elif existing in _EARNINGS_PERSIST_SAFE_STATUS:
                status = existing
            else:
                status = _earnings_note_to_status_code(
                    getattr(e, "note", None),
                    getattr(e, "earnings_block", None),
                    getattr(e, "earnings_days", None),
                )
            # R25.7: Only persist safe statuses; never EARNINGS_NOT_EVALUATED
            if status not in _EARNINGS_PERSIST_SAFE_STATUS:
                status = "OK" if status == "EARNINGS_OK" else "Unavailable"
            d["status_code"] = status
            return d

        # R22.9: DO NOT persist diagnostics_by_symbol; diagnostics is request-time only.
        return {
            "metadata": self.metadata,
            "symbols": [symbol_persist(s) for s in self.symbols],
            "selected_candidates": [candidate_persist(c) for c in self.selected_candidates],
            "candidates_by_symbol": {
                k: [candidate_persist(c) for c in v]
                for k, v in self.candidates_by_symbol.items()
            },
            "gates_by_symbol": {
                k: [gate_persist(g) for g in v]
                for k, v in self.gates_by_symbol.items()
            },
            "earnings_by_symbol": {
                k: earnings_persist(v) for k, v in self.earnings_by_symbol.items()
            },
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionArtifactV2":
        meta = data.get("metadata") or {}
        sym_fields = {f.name for f in SymbolEvalSummary.__dataclass_fields__.values()}
        symbols = []
        for s in data.get("symbols") or []:
            row = s if isinstance(s, dict) else asdict(s)
            d = {k: v for k, v in row.items() if k in sym_fields}
            # R22.7: backward compat — derive primary_reason_codes from primary_reason if missing
            if not d.get("primary_reason_codes") and d.get("primary_reason"):
                d["primary_reason_codes"] = _reason_string_to_codes(d.get("primary_reason"))
            # R22.7: do not keep prose in memory; API derives display from primary_reason_codes
            if d.get("primary_reason_codes") is not None:
                d["primary_reason"] = None
            # Band never null: derive from final_score only (Phase 10.1)
            if d.get("band") not in ("A", "B", "C", "D"):
                d["band"] = assign_band(d.get("final_score") or d.get("score"))
            symbols.append(SymbolEvalSummary(**d))
        cand_fields = {f.name for f in CandidateRow.__dataclass_fields__.values()}
        selected = []
        for c in data.get("selected_candidates") or []:
            row = c if isinstance(c, dict) else asdict(c)
            d = {k: row.get(k) for k in cand_fields}
            # R23.1: Normalize contract_key on load (e.g. 673.0-... -> 673-...)
            ck = d.get("contract_key")
            if isinstance(ck, str) and ".0-" in ck:
                try:
                    pre, rest = ck.split(".0-", 1)
                    if pre.isdigit() or (pre.replace(".", "", 1).isdigit()):
                        d["contract_key"] = f"{int(float(pre))}-{rest}"
                except Exception:
                    pass
            selected.append(CandidateRow(**d))
        cb = data.get("candidates_by_symbol") or {}
        candidates_by_symbol = {}
        for k, v in cb.items():
            list_c = []
            for c in v:
                if isinstance(c, dict):
                    d = {x: c.get(x) for x in cand_fields}
                    for key in cand_fields:
                        if key not in d:
                            d[key] = None
                    ck = d.get("contract_key")
                    if isinstance(ck, str) and ".0-" in ck:
                        try:
                            pre, rest = ck.split(".0-", 1)
                            if pre.isdigit() or (pre.replace(".", "", 1).isdigit()):
                                d["contract_key"] = f"{int(float(pre))}-{rest}"
                        except Exception:
                            pass
                    list_c.append(CandidateRow(**d))
                else:
                    list_c.append(c)
            candidates_by_symbol[k] = list_c
        gb = data.get("gates_by_symbol") or {}
        gate_fields = {f.name for f in GateEvaluation.__dataclass_fields__.values()}
        gates_by_symbol = {}
        for k, v in gb.items():
            gates_by_symbol[k] = []
            for g in v:
                if isinstance(g, dict):
                    # R23.2: Backward compat — new format has gate_code; old has name
                    code = g.get("gate_code")
                    if code and _STRICT_CODE_RE.match(str(code)):
                        name = gate_code_to_label(code)
                    else:
                        name = g.get("name") or "Gate"
                        code = gate_name_to_code(name)
                    d = {"name": name, "status": g.get("status", "SKIP"), "reason": g.get("reason"), "gate_code": code}
                    gates_by_symbol[k].append(GateEvaluation(**d))
                else:
                    gates_by_symbol[k].append(g)
        eb = data.get("earnings_by_symbol") or {}
        _earnings_fields = {f.name for f in EarningsInfo.__dataclass_fields__.values()}
        earnings_by_symbol = {}
        for k, v in eb.items():
            if isinstance(v, dict):
                d = {x: v[x] for x in v if x in _earnings_fields}
                d.setdefault("note", None)  # R22.7 Fix Pack: persisted has status_code only
                earnings_by_symbol[k] = EarningsInfo(**d)
            else:
                earnings_by_symbol[k] = v
        db = data.get("diagnostics_by_symbol") or {}
        diag_fields = {f.name for f in SymbolDiagnosticsDetails.__dataclass_fields__.values()}
        _empty: Dict[str, Any] = {}
        diagnostics_by_symbol = {}
        for k, v in db.items():
            if isinstance(v, dict):
                d = {x: (v[x] if x in v else (_empty if x in ("technicals", "exit_plan", "risk_flags", "explanation", "stock", "symbol_eligibility", "liquidity", "options") else None))
                     for x in diag_fields}
                diagnostics_by_symbol[k] = SymbolDiagnosticsDetails(**d)
            elif isinstance(v, SymbolDiagnosticsDetails):
                diagnostics_by_symbol[k] = v
        return cls(
            metadata=meta,
            symbols=symbols,
            selected_candidates=selected,
            candidates_by_symbol=candidates_by_symbol,
            gates_by_symbol=gates_by_symbol,
            earnings_by_symbol=earnings_by_symbol,
            diagnostics_by_symbol=diagnostics_by_symbol,
            warnings=data.get("warnings") or [],
        )
