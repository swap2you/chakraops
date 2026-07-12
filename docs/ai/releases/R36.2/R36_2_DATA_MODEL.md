# R36.2 — Universe V2 — Data Model

All types are additive and defined in `chakraops/app/core/universe_v2/model.py`.
Persistence lives under the output dir (`out/` by default) in `universe_v2/`.

## Enums / constants
- Lifecycle states: `ADMITTED`, `WATCH`, `QUARANTINE`, `REMOVED`.
- Strategies: `CORE_WHEEL`, `BALANCED_WHEEL`, `AGGRESSIVE_WHEEL`, `SHARES`.
- Membership status: `ELIGIBLE`, `NOT_ELIGIBLE`, `NOT_EVALUATED`.
- Schema version: `SCHEMA_VERSION = "univ2.v1"`.

## `StrategyMembership`
- `strategy: str` (one of the four)
- `status: str` (`ELIGIBLE`/`NOT_ELIGIBLE`/`NOT_EVALUATED`)
- `primary_reason: dict | None` (registry-resolved ReasonCode.to_dict())
- `supporting_reasons: list[dict]`
- `measured: float | None`, `threshold: float|list|None`, `unit: str|None`

## `LifecycleTransition`
- `from_state: str | None`, `to_state: str`, `reason_code: str`, `at_utc: str`

## `ManualOverride`
- `kind: str` (`INCLUDE`/`EXCLUDE`) — mirrors the effective overlay
- `reason: str | None`, `at_utc: str | None`
- Overrides are explicit, logged, reversible. An override can NEVER move a symbol out of
  `QUARANTINE` while a safety-critical/stale-data reason is present (enforced in policy).

## `UniverseV2Record` (per symbol)
- `symbol: str`
- `in_research_pool: bool`
- `lifecycle_state: str`
- `memberships: dict[str, StrategyMembership]` (keyed by strategy)
- `primary_reason: dict | None`, `supporting_reasons: list[dict]`
- `safety_critical: bool`, `temporary: bool`
- `pass_streak: int`, `fail_streak: int`
- `last_transition: LifecycleTransition | None`
- `evaluation_version: str | None` (source artifact run_id)
- `data_source: str | None` (e.g. `ORATS`), `as_of_utc: str | None`
- `manual_override: ManualOverride | None`

## `UniverseV2Snapshot` (published, versioned)
- `schema_version: str`
- `version: int` (monotonic; increments per successful publish)
- `created_at_utc: str`
- `status: str` (`COMPLETE`/`STALE`/`FAILED`)
- `source_evaluation_version: str | None`
- `research_pool_count: int`
- `records: list[UniverseV2Record]`
- `counts: dict` (lifecycle funnel + per-strategy eligible counts + rejection funnel + top reasons)

## Persistence layout (`<out>/universe_v2/`)
- `lifecycle_state.json` — durable per-symbol lifecycle + streaks + transition history + overrides. Written atomically (temp+fsync+replace) under a cross-process lock.
- `snapshot_latest.json` — the published read snapshot (authoritative read source).
- `snapshots/<version>.json` — immutable per-version copies (retention: keep last N).
- `lifecycle_state.bak.json` — single-slot backup for rollback/containment.

## Transactionality / versioning
- One publish = acquire lock → update durable state → write new versioned snapshot (temp+rename) → atomically swap `snapshot_latest.json`. No mixed partial versions.
- On build/refresh failure the previous good `snapshot_latest.json` is preserved and marked `STALE` only via a status field on read (never overwritten with partial data).
