# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.4: Ticker Copilot v1 — read-only. R23.4.1: auth + error handling. R23.4.2: key parsing + validation."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.api.ui_routes import (
    _require_ui_key,
    get_symbol_diagnostics_for_copilot,
    get_universe_row_for_copilot,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])

COPILOT_OPENAI_MODEL = (os.getenv("COPILOT_OPENAI_MODEL") or "gpt-4o").strip()
COPILOT_MAX_TOOL_ROUNDS = 5

# Error codes (never log or return full API keys).
COPILOT_KEY_MISSING = "COPILOT_KEY_MISSING"
COPILOT_KEY_MALFORMED = "COPILOT_KEY_MALFORMED"
COPILOT_AUTH_FAILED = "COPILOT_AUTH_FAILED"
COPILOT_UPSTREAM_UNAVAILABLE = "COPILOT_UPSTREAM_UNAVAILABLE"
COPILOT_INTERNAL_ERROR = "COPILOT_INTERNAL_ERROR"

# R23.4.3: Last Copilot error code (set on 502/503/500); exposed in system-health only.
LAST_COPILOT_ERROR_CODE: Optional[str] = None


def _clean_api_key(v: str | None) -> str | None:
    """
    R23.4.3: Clean env key value — strip whitespace, remove surrounding quotes, return None if empty.
    Does not strip VAR= prefix (handled in _get_copilot_api_key).
    """
    if v is None:
        return None
    s = (v or "").strip()
    if not s:
        return None
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        s = s[1:-1].strip()
    return s if s else None


def _normalize_copilot_key(raw: str) -> str:
    """Strip whitespace, surrounding quotes, and accidental VAR= prefix. Does not check internal whitespace."""
    if not raw:
        return ""
    s = raw.strip()
    # Remove surrounding single or double quotes
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        s = s[1:-1].strip()
    # Defensive: remove pasted line prefix OPENAI_API_KEY= or COPILOT_OPENAI_API_KEY=
    for prefix in ("COPILOT_OPENAI_API_KEY=", "OPENAI_API_KEY="):
        if s.upper().startswith(prefix):
            s = s[len(prefix):].strip()
            break
    return s


def _validate_key_format(key: str) -> Tuple[bool, Optional[str]]:
    """
    Minimal format checks: startswith sk-, length >= 20, no spaces/newlines/tabs.
    Returns (True, None) if valid; (False, error_code) if invalid.
    """
    if not key:
        return (False, COPILOT_KEY_MISSING)
    k = key.strip()
    if not k:
        return (False, COPILOT_KEY_MISSING)
    if not k.startswith("sk-"):
        return (False, COPILOT_KEY_MALFORMED)
    if len(k) < 20:
        return (False, COPILOT_KEY_MALFORMED)
    if any(c in k for c in (" ", "\n", "\r", "\t")):
        return (False, COPILOT_KEY_MALFORMED)
    return (True, None)


def _get_copilot_key_and_source() -> Tuple[Optional[str], str]:
    """
    R23.4.3: Return (cleaned_key, key_source). key_source is COPILOT_OPENAI_API_KEY, OPENAI_API_KEY, or NONE.
    Uses _clean_api_key; strips pasted VAR= prefix; rejects internal whitespace and invalid format.
    """
    for env_key in ("COPILOT_OPENAI_API_KEY", "OPENAI_API_KEY"):
        raw = os.getenv(env_key)
        cleaned = _clean_api_key(raw)
        if not cleaned:
            continue
        for prefix in ("COPILOT_OPENAI_API_KEY=", "OPENAI_API_KEY="):
            if cleaned.upper().startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()
                break
        if not cleaned or any(c in cleaned for c in (" ", "\n", "\r", "\t")):
            continue
        ok, _ = _validate_key_format(cleaned)
        if ok:
            return (cleaned, env_key)
    return (None, "NONE")


def _get_copilot_key_present() -> bool:
    """True if any env var has a non-empty value after _clean_api_key (even if malformed)."""
    c1 = _clean_api_key(os.getenv("COPILOT_OPENAI_API_KEY"))
    c2 = _clean_api_key(os.getenv("OPENAI_API_KEY"))
    return bool(c1 or c2)


def get_copilot_status() -> Dict[str, Any]:
    """
    R23.4.2/R23.4.3: Status only, no secrets. For system-health and startup log.
    Returns: enabled, key_present, key_format_ok, key_source, model, last_error_code.
    """
    key, key_source = _get_copilot_key_and_source()
    key_present = _get_copilot_key_present()
    key_format_ok = key is not None
    enabled = key_format_ok
    return {
        "enabled": enabled,
        "key_present": key_present,
        "key_format_ok": key_format_ok,
        "key_source": key_source,
        "model": COPILOT_OPENAI_MODEL,
        "last_error_code": LAST_COPILOT_ERROR_CODE,
    }


def _get_copilot_api_key() -> Optional[str]:
    """
    R23.4.2/R23.4.3: Robust key parsing. COPILOT_OPENAI_API_KEY then OPENAI_API_KEY.
    Uses _clean_api_key; strips VAR= prefix; rejects internal whitespace or invalid format.
    Returns None if missing or malformed.
    """
    key, _ = _get_copilot_key_and_source()
    return key


_copilot_startup_logged = False


def _copilot_startup_log() -> None:
    """Single-line startup log; never print the key. R23.4.2: includes key_format_ok."""
    global _copilot_startup_logged
    if _copilot_startup_logged:
        return
    _copilot_startup_logged = True
    status = get_copilot_status()
    logger.info(
        "[COPILOT] enabled=%s key_present=%s key_format_ok=%s model=%s",
        status["enabled"],
        status["key_present"],
        status["key_format_ok"],
        status["model"],
    )


def _redact_sk(msg: str) -> str:
    """Redact sk- prefix in error messages (never log full keys)."""
    if not msg:
        return msg
    return re.sub(r"sk-[a-zA-Z0-9]+", "sk-***", msg)

# Allowlisted doc paths for search_docs (relative to repo root). Phase 23 + enhancements only.
COPILOT_DOCS_ALLOWLIST: List[str] = [
    "docs/releases/R23.0_requirements.md",
    "docs/releases/R23.0_release_notes.md",
    "docs/releases/R23.1_requirements.md",
    "docs/releases/R23.1_release_notes.md",
    "docs/releases/R23.2_requirements.md",
    "docs/releases/R23.2_release_notes.md",
    "docs/releases/R23.3_requirements.md",
    "docs/releases/R23.3_release_notes.md",
    "docs/releases/R23.4_requirements.md",
    "docs/releases/R23.4_release_notes.md",
    "chakraops/docs/enhancements/phase_22_trading_intelligence_and_prod_readiness.md",
    "chakraops/docs/releases/RELEASE_CHECKLIST.md",
]

# Forbidden patterns in model output — replace with safe message if detected
COPILOT_FORBIDDEN_PATTERNS = [
    re.compile(r"FAIL_[A-Z0-9_]+", re.I),
    re.compile(r"WARN_[A-Z0-9_]+", re.I),
    re.compile(r"api[_\s]?key", re.I),
    re.compile(r"\b(token|secret|password)\s*[:=]", re.I),
    re.compile(r"/[a-z]+/[a-z0-9_.-]+\.(json|key|env)", re.I),
]


def _repo_root() -> Path:
    """Workspace root (parent of chakraops) so docs/releases and chakraops/docs both resolve."""
    return Path(__file__).resolve().parents[3]


def _run_tool(name: str, arguments: Dict[str, Any], symbol: Optional[str]) -> Dict[str, Any]:
    """Execute a single read-only tool. Only allowlisted tools; no write endpoints."""
    try:
        if name == "get_symbol_diagnostics":
            sym = (arguments.get("symbol") or symbol or "").strip().upper()
            if not sym:
                return {"error": "symbol is required"}
            out = get_symbol_diagnostics_for_copilot(sym)
            if out is None:
                return {"error": f"Symbol {sym} not in evaluation store. Suggest user run evaluation or recompute."}
            return _compact_for_tool(out, max_chars=6000)

        if name == "get_decision_latest":
            from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
            store = get_evaluation_store_v2()
            store.reload_from_disk()
            artifact = store.get_latest()
            if artifact is None:
                return {"error": "No decision artifact; run evaluation."}
            d = artifact.to_dict()
            meta = d.get("metadata") or {}
            return {
                "evaluation_timestamp_utc": meta.get("pipeline_timestamp"),
                "run_id": meta.get("run_id"),
                "symbols_count": len(d.get("symbols") or []),
                "symbols_summary": [
                    {"symbol": s.get("symbol"), "verdict": s.get("verdict"), "band": s.get("band"), "score": s.get("score")}
                    for s in (d.get("symbols") or [])[:30]
                ],
            }

        if name == "get_universe_row":
            sym = (arguments.get("symbol") or symbol or "").strip().upper()
            if not sym:
                return {"error": "symbol is required"}
            row = get_universe_row_for_copilot(sym)
            if row is None:
                return {"error": f"Symbol {sym} not in universe."}
            return _compact_for_tool(row, max_chars=2000)

        if name == "get_positions_tracked":
            from app.core.positions.service import list_positions
            positions = list_positions(status=None, symbol=None, exclude_test=True)
            out = [p.to_dict() for p in positions]
            return {"positions": out[:50], "count": len(positions)}

        if name == "get_account_default":
            from app.core.accounts.service import get_default_account
            acc = get_default_account()
            if acc is None:
                return {"account": None, "message": "No default account set"}
            return {"account": acc.to_dict()}

        if name == "get_account_holdings":
            # Prefer fresh LIVE broker equity lens; manual recovery labeled separately.
            try:
                from app.core.portfolio.live_position_lenses_r70 import build_live_position_lenses

                lenses = build_live_position_lenses()
                live = (lenses.get("lenses") or {}).get("LIVE_BROKER_EQUITY_POSITIONS") or {}
                items = live.get("items") or []
                if lenses.get("live_state") == "FRESH" and items:
                    return {
                        "holdings": items,
                        "source": "LIVE_BROKER",
                        "as_of": lenses.get("as_of"),
                        "live_state": lenses.get("live_state"),
                        "count": len(items),
                    }
                manual = (lenses.get("lenses") or {}).get("MANUAL_RECOVERY_POSITIONS") or {}
                return {
                    "holdings": manual.get("items") or [],
                    "source": "MANUAL_RECOVERY",
                    "as_of": None,
                    "live_state": lenses.get("live_state"),
                    "count": len(manual.get("items") or []),
                    "note": "Broker LIVE unavailable or empty; showing labeled manual recovery only.",
                }
            except Exception:
                from app.core.accounts.holdings_db import list_holdings
                holdings = list_holdings()
                return {"holdings": holdings, "source": "MANUAL_RECOVERY", "note": "fallback"}

        if name == "get_share_position":
            sym = (arguments.get("symbol") or symbol or "").strip().upper()
            aid = (arguments.get("account_id") or "").strip()
            if not aid:
                from app.core.accounts.holdings_db import _DEFAULT_ACCOUNT_ID
                aid = _DEFAULT_ACCOUNT_ID
            if not sym:
                return {"error": "symbol is required"}
            from app.core.accounts.holdings_db import get_share_position
            pos = get_share_position(aid, sym)
            if pos is None:
                return {"position": None, "message": f"No share position for {sym}"}
            return pos

        if name == "get_delta_override":
            sym = (arguments.get("symbol") or symbol or "").strip().upper()
            if not sym:
                return {"error": "symbol is required"}
            from app.core.config.delta_overrides import load_delta_overrides
            overrides = load_delta_overrides()
            if sym in overrides:
                return {"symbol": sym, "override": overrides[sym]}
            return {"symbol": sym, "override": None}

        if name == "get_system_health":
            return _get_system_health_for_copilot()

        if name == "search_docs":
            query = (arguments.get("query") or "").strip()
            if not query:
                return {"snippets": [], "message": "query is required"}
            snippets = _search_docs_allowlisted(query, max_total_chars=800)
            return {"snippets": snippets}

        return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"error": str(e)}


def _get_system_health_for_copilot() -> Dict[str, Any]:
    """Build a compact system health dict for copilot (no auth). Same data sources as /api/ui/system-health."""
    out: Dict[str, Any] = {"api": {"status": "OK"}, "orats": {}, "market": {}, "scheduler": {}}
    try:
        from app.api.data_health import get_data_health, get_orats_freshness_state
        dh = get_data_health()
        out["orats"] = {
            "status": dh.get("status"),
            "last_success_at": dh.get("last_success_at") or dh.get("effective_last_success_at"),
            "age_minutes": None,
        }
        if out["orats"].get("last_success_at"):
            from datetime import datetime, timezone
            try:
                success_dt = datetime.fromisoformat(str(out["orats"]["last_success_at"]).replace("Z", "+00:00"))
                out["orats"]["age_minutes"] = round((datetime.now(timezone.utc) - success_dt).total_seconds() / 60, 1)
            except (ValueError, TypeError):
                pass
        fresh = get_orats_freshness_state()
        out["orats"]["freshness_state"] = fresh.get("state")
        out["orats"]["freshness_label"] = fresh.get("state_label")
    except Exception as e:
        from app.core.security.redact import redact_secrets
        out["orats"] = {"status": "DOWN", "error": redact_secrets(str(e))}
    try:
        from app.market.market_hours import get_market_phase
        out["market"]["phase"] = get_market_phase() or "UNKNOWN"
        out["market"]["is_open"] = (out["market"].get("phase") or "").upper() == "OPEN"
    except Exception as e:
        out["market"] = {"phase": "UNKNOWN", "error": str(e)}
    try:
        from app.api.server import get_scheduler_status
        sched = get_scheduler_status()
        out["scheduler"] = {
            "last_run_at": sched.get("last_run_at"),
            "last_result": sched.get("last_result"),
            "last_skip_reason": sched.get("last_skip_reason"),
            "next_run_at": sched.get("next_run_at"),
        }
    except Exception as e:
        out["scheduler"] = {"error": str(e)}
    return out


def _compact_for_tool(obj: Any, max_chars: int = 4000) -> Dict[str, Any]:
    """Return a compact JSON-serializable dict; truncate long string values."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        total = 0
        for k, v in obj.items():
            if total >= max_chars:
                break
            if isinstance(v, (str, bytes)):
                s = v[:500] if isinstance(v, str) else v.decode("utf-8", errors="replace")[:500]
                out[k] = s
                total += len(s)
            elif isinstance(v, (int, float, bool)) or v is None:
                out[k] = v
            elif isinstance(v, (list, dict)):
                out[k] = _compact_for_tool(v, max_chars=max_chars - total)
                total += len(json.dumps(out[k]))
            else:
                out[k] = str(v)[:200]
                total += len(out[k])
        return out
    if isinstance(obj, list):
        return {"items": [_compact_for_tool(x, max_chars=max_chars // max(1, len(obj))) for x in obj[:20]]}
    return {"value": str(obj)[:500]}


def _search_docs_allowlisted(query: str, max_total_chars: int = 800) -> List[Dict[str, Any]]:
    """Search only allowlisted doc files; return snippets (file name + excerpt)."""
    root = _repo_root()
    snippets: List[Dict[str, Any]] = []
    total = 0
    q_lower = query.lower()
    for rel in COPILOT_DOCS_ALLOWLIST:
        if total >= max_total_chars:
            break
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if total >= max_total_chars:
                break
            if q_lower in line.lower():
                excerpt = line.strip()[:200]
                snippets.append({"file": rel, "line": i + 1, "excerpt": excerpt})
                total += len(excerpt) + 50
    return snippets[:15]


def _sanity_answer(text: str) -> str:
    """Replace response if it contains forbidden patterns (FAIL_*, WARN_*, secrets, etc.)."""
    if not text:
        return text
    for pat in COPILOT_FORBIDDEN_PATTERNS:
        if pat.search(text):
            return (
                "I don't have enough data to answer that safely. "
                "Try running an evaluation or symbol recompute, then ask again. "
                "Do not share API keys, tokens, or internal paths."
            )
    return text


def _openai_chat_with_tools(
    system_prompt: str,
    user_message: str,
    symbol: Optional[str],
    tools_schema: List[Dict[str, Any]],
) -> tuple[str, List[str], List[Dict[str, Any]], bool]:
    """Call OpenAI chat completions with tool handling. Returns (answer_markdown, used_tools, citations, snapshot_used). Caller must ensure key is present (503 at endpoint if missing)."""
    api_key = _get_copilot_api_key()
    if not api_key:
        return (
            "Copilot is not configured. Set COPILOT_OPENAI_API_KEY (or OPENAI_API_KEY) on the server and restart.",
            [],
            [],
            False,
        )

    try:
        from openai import OpenAI
    except ImportError:
        return (
            "OpenAI package is not installed. Add 'openai' to requirements to enable Copilot.",
            [],
            [],
            False,
        )

    client = OpenAI(api_key=api_key)
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    used_tools: List[str] = []
    citations: List[Dict[str, str]] = []
    snapshot_used = False

    for _ in range(COPILOT_MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=COPILOT_OPENAI_MODEL,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
        )
        choice = response.choices[0] if response.choices else None
        if not choice:
            break
        msg = choice.message
        if getattr(msg, "content", None) and msg.content:
            answer = _sanity_answer(msg.content.strip())
            return (answer, used_tools, citations, snapshot_used)
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            break
        messages.append(msg)
        for tc in tool_calls:
            name = getattr(tc.function, "name", None) or (tc.function.get("name") if isinstance(tc.function, dict) else None)
            args_str = getattr(tc.function, "arguments", None) or (tc.function.get("arguments") if isinstance(tc.function, dict) else "")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else (args_str or {})
            except json.JSONDecodeError:
                args = {}
            used_tools.append(name)
            result = _run_tool(name, args, symbol)
            citations.append({"tool": name, "at": str(uuid.uuid4())[:8]})
            if "snapshot" in str(result).lower() or "as_of" in str(result).lower():
                snapshot_used = True
            messages.append({
                "role": "tool",
                "tool_call_id": getattr(tc, "id", None) or "",
                "content": json.dumps(result)[:8000],
            })
    return (
        "I don't have enough data to answer that. Try running an evaluation (eval/run) or symbol recompute, then ask again.",
        used_tools,
        citations,
        snapshot_used,
    )


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_symbol_diagnostics",
            "description": "Get full symbol diagnostics for a ticker (verdict, gates, delta, shares plan, support/resistance). Use for 'why not eligible', 'what delta', 'support levels'.",
            "parameters": {"type": "object", "properties": {"symbol": {"type": "string", "description": "Ticker symbol"}}, "required": ["symbol"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_decision_latest",
            "description": "Get latest decision artifact summary (evaluation timestamp, symbols count, per-symbol verdict/band/score).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_universe_row",
            "description": "Get one symbol's row from the universe (score, band, primary_reason, shares_eligible).",
            "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_positions_tracked",
            "description": "List tracked positions (options and stock).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_default",
            "description": "Get default account (capital, etc.).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_holdings",
            "description": "List holdings for default account.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_share_position",
            "description": "Get share position for symbol and account.",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "account_id": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_delta_override",
            "description": "Get delta band override for a symbol if any.",
            "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_health",
            "description": "System health: API, ORATS data freshness, market phase, scheduler. Use for 'is data fresh?'.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search allowlisted docs (release notes, requirements) for concepts.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
]

SYSTEM_PROMPT = """You are a read-only ChakraOps Ticker Copilot. You help users understand symbol diagnostics, eligibility, and system state.

Rules:
- Only use the provided tools to get facts. Do not invent numbers, scores, IVR, or verdicts.
- Cite tool source and as_of when presenting portfolio or score facts. Prefer LIVE_BROKER holdings over manual recovery.
- Never claim the portfolio is empty when LIVE broker holdings are present in tool output.
- Do not invent stage-1 score components; if score_basis is stage1_score, describe only published stage1 fields.
- Do not give financial advice beyond describing what ChakraOps outputs show.
- Do not recommend placing orders; you can describe what the system indicates (e.g. eligible, delta band).
- Never reveal API keys, tokens, internal file paths, or secrets.
- In your answers, use safe labels only: e.g. "Eligible" / "Not eligible", "Delayed" / "Stale", "Regime conflict", "Not near support". Do NOT output raw codes like FAIL_* or WARN_*.
- If evidence is missing, say you don't have enough data and suggest running evaluation or symbol recompute.
- Keep answers concise and grounded in tool outputs."""


@router.post("/ask")
async def copilot_ask(
    body: Dict[str, Any],
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
):
    """
    R23.4: Ask the copilot a question. Read-only. R23.4.1: returns 503/502/500 with error_code + message on config/OpenAI errors.
    """
    _require_ui_key(x_ui_key)
    _copilot_startup_log()

    symbol = (body.get("symbol") or "").strip().upper()
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    global LAST_COPILOT_ERROR_CODE
    status = get_copilot_status()
    if not status["key_present"]:
        LAST_COPILOT_ERROR_CODE = COPILOT_KEY_MISSING
        logger.warning("Copilot request rejected: key missing (503)")
        return JSONResponse(
            status_code=503,
            content={
                "error_code": COPILOT_KEY_MISSING,
                "message": "Copilot is disabled on this server. Set COPILOT_OPENAI_API_KEY (or OPENAI_API_KEY) and restart.",
            },
        )
    if not status["key_format_ok"]:
        LAST_COPILOT_ERROR_CODE = COPILOT_KEY_MALFORMED
        logger.warning("Copilot request rejected: key malformed (503)")
        return JSONResponse(
            status_code=503,
            content={
                "error_code": COPILOT_KEY_MALFORMED,
                "message": "Copilot API key looks malformed (quotes, spaces, or invalid format). Fix .env and restart.",
            },
        )
    mode = (body.get("mode") or "symbol").strip().lower()
    if mode not in ("symbol", "general"):
        mode = "symbol"

    user_message = question
    if symbol and mode == "symbol":
        user_message = f"Symbol context: {symbol}. Question: {question}"

    try:
        answer_md, used_tools, citations, snapshot_used = _openai_chat_with_tools(
            SYSTEM_PROMPT, user_message, symbol or None, TOOLS_SCHEMA
        )
    except Exception as e:
        err_type = type(e).__name__
        err_msg = _redact_sk(str(e))
        if "AuthenticationError" in err_type or "invalid_api_key" in err_msg.lower() or "401" in err_msg:
            LAST_COPILOT_ERROR_CODE = COPILOT_AUTH_FAILED
            logger.warning("Copilot auth failed: error_code=%s status=502 msg=%s", COPILOT_AUTH_FAILED, _redact_sk(err_msg[:200]))
            return JSONResponse(
                status_code=502,
                content={
                    "error_code": COPILOT_AUTH_FAILED,
                    "message": "Copilot authentication failed.",
                },
            )
        if "HTTPStatusError" in err_type or "RateLimitError" in err_type or "429" in err_msg or "503" in err_msg:
            LAST_COPILOT_ERROR_CODE = COPILOT_UPSTREAM_UNAVAILABLE
            logger.warning("Copilot upstream unavailable: error_code=%s status=503 msg=%s", COPILOT_UPSTREAM_UNAVAILABLE, _redact_sk(err_msg[:200]))
            return JSONResponse(
                status_code=503,
                content={
                    "error_code": COPILOT_UPSTREAM_UNAVAILABLE,
                    "message": "Copilot upstream is temporarily unavailable. Try again later.",
                },
            )
        LAST_COPILOT_ERROR_CODE = COPILOT_INTERNAL_ERROR
        logger.exception("Copilot internal error: error_code=%s status=500", COPILOT_INTERNAL_ERROR)
        return JSONResponse(
            status_code=500,
            content={
                "error_code": COPILOT_INTERNAL_ERROR,
                "message": "An unexpected error occurred. Check server logs.",
            },
        )

    followups = []
    if "eligible" in question.lower() or "why" in question.lower():
        followups.append("What delta missed the band and by how much?")
    if "delta" in question.lower():
        followups.append("What are the key support/resistance levels?")
    followups.extend(["What is my position/holdings exposure?", "Is data fresh and scheduler healthy?"])
    followups = list(dict.fromkeys(followups))[:4]

    # Clear stale error after a successful ask (R70-DEF-060 honesty).
    LAST_COPILOT_ERROR_CODE = None
    request_id = str(uuid.uuid4())
    return {
        "answer_markdown": answer_md,
        "citations": citations,
        "followups": followups,
        "used_tools": used_tools,
        "snapshot_used": snapshot_used,
        "request_id": request_id,
        "last_error_code": None,
    }
