# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Authoritative mapping: mutable store path → writer lock → snapshot procedure."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Iterable, List, Optional, Tuple

from app.core.universe.refresh_lock import RefreshLockTimeout


@dataclass(frozen=True)
class SnapshotTarget:
    source: Path
    writer_lock_kind: str
    writer_lock_name: str
    consistency_method: str
    snapshot_procedure: str


# Global lock acquisition order (deadlock prevention).
_LOCK_ORDER = {
    "cross_process:job_incidents": 10,
    "cross_process:job_run_store": 20,
    "cross_process:scheduler_occurrences": 30,
    "cross_process:weekly_refresh": 40,
    "file_lock": 50,
}


def _lock_sort_key(kind: str, name: str) -> Tuple[int, str]:
    return (_LOCK_ORDER.get(f"{kind}:{name}", _LOCK_ORDER.get(kind, 99)), name)


def _refresh_history_path() -> Path:
    from app.core.universe.refresh_history_store import RefreshHistoryStore

    return RefreshHistoryStore().path


def _notifications_path() -> Path:
    from app.api.notifications_store import _notifications_path

    return _notifications_path()


def build_snapshot_targets(out_dir: Path) -> List[SnapshotTarget]:
    """Return every R35 mutable JSON/JSONL store and its true writer lock."""
    out = Path(out_dir)
    targets: List[SnapshotTarget] = [
        SnapshotTarget(
            source=out / "job_runs.jsonl",
            writer_lock_kind="cross_process",
            writer_lock_name="job_run_store",
            consistency_method="writer_cross_process_lock_snapshot",
            snapshot_procedure="Acquire job_run_store lock; read full bytes",
        ),
        SnapshotTarget(
            source=out / "scheduler_occurrences.jsonl",
            writer_lock_kind="cross_process",
            writer_lock_name="scheduler_occurrences",
            consistency_method="writer_cross_process_lock_snapshot",
            snapshot_procedure="Acquire scheduler_occurrences lock; read full bytes",
        ),
        SnapshotTarget(
            source=out / "job_incidents.jsonl",
            writer_lock_kind="cross_process",
            writer_lock_name="job_incidents",
            consistency_method="writer_cross_process_lock_snapshot",
            snapshot_procedure="Acquire job_incidents lock; read full bytes",
        ),
        SnapshotTarget(
            source=_notifications_path(),
            writer_lock_kind="file_lock",
            writer_lock_name=str(_notifications_path()),
            consistency_method="writer_file_lock_snapshot",
            snapshot_procedure="Acquire notifications with_file_lock; read full bytes",
        ),
        SnapshotTarget(
            source=_refresh_history_path(),
            writer_lock_kind="cross_process",
            writer_lock_name="weekly_refresh",
            consistency_method="writer_cross_process_lock_snapshot",
            snapshot_procedure="Acquire weekly_refresh lock; read full bytes",
        ),
    ]
    known = {t.source.name for t in targets}
    for pattern in ("*.jsonl", "*.json"):
        for src in out.glob(pattern):
            if src.name in known:
                continue
            if src.name.endswith(".journal.json") or src.name == "process_ownership.json":
                continue
            targets.append(
                SnapshotTarget(
                    source=src,
                    writer_lock_kind="file_lock",
                    writer_lock_name=str(src),
                    consistency_method="writer_file_lock_snapshot",
                    snapshot_procedure=f"Acquire with_file_lock({src.name}); read full bytes",
                )
            )
            known.add(src.name)
    return targets


@contextmanager
def acquire_writer_locks(
    targets: Iterable[SnapshotTarget],
    *,
    cross_process_timeout: float = 10.0,
    file_lock_timeout_ms: int = 5000,
) -> Generator[None, None, None]:
    """Acquire all distinct writer locks in deterministic global order."""
    from app.core.io.locks import with_file_lock
    from app.core.universe.refresh_lock import cross_process_lock

    unique: dict[Tuple[str, str], SnapshotTarget] = {}
    for t in targets:
        key = (t.writer_lock_kind, t.writer_lock_name)
        unique.setdefault(key, t)
    ordered = sorted(unique.values(), key=lambda t: _lock_sort_key(t.writer_lock_kind, t.writer_lock_name))

    stack = ExitStack()
    try:
        for t in ordered:
            if t.writer_lock_kind == "cross_process":
                stack.enter_context(
                    cross_process_lock(t.writer_lock_name, timeout=cross_process_timeout)
                )
            elif t.writer_lock_kind == "file_lock":
                stack.enter_context(
                    with_file_lock(Path(t.writer_lock_name), timeout_ms=file_lock_timeout_ms)
                )
            else:
                raise RefreshLockTimeout(f"unknown writer lock kind: {t.writer_lock_kind}")
        yield
    except TimeoutError as exc:
        raise RefreshLockTimeout(str(exc)) from exc
    finally:
        stack.close()


def snapshot_bytes(target: SnapshotTarget) -> bytes:
    """Read source bytes; caller must hold writer locks via acquire_writer_locks."""
    if not target.source.exists():
        return b""
    return target.source.read_bytes()


def writer_lock_mapping_documentation() -> str:
    lines = ["| path | writer lock | snapshot procedure |", "|---|---|---|"]
    try:
        from app.core.settings import get_output_dir

        out = Path(get_output_dir())
    except Exception:
        out = Path("out")
    for t in build_snapshot_targets(out):
        lock = f"{t.writer_lock_kind}:{t.writer_lock_name}"
        lines.append(f"| `{t.source}` | `{lock}` | {t.snapshot_procedure} |")
    return "\n".join(lines)
