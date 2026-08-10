# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 threshold provenance registry.

Runtime decisioning continues to read ``config/strategy_profiles.yaml``.
This module loads ``config/threshold_registry.yaml`` and exposes
``get_threshold_provenance(profile, key)`` so operators can see whether a
threshold is inherited or calibrated (with optional evidence_path).

No silent retunes: calibrated without evidence_path is rejected at load.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


class ThresholdRegistryError(ValueError):
    """Invalid threshold registry configuration."""


ALLOWED_SOURCES = frozenset({"inherited", "calibrated"})


@dataclass(frozen=True)
class ThresholdProvenance:
    profile: str
    key: str
    source: str
    evidence_path: Optional[str] = None
    runtime_source: str = "strategy_profiles.yaml"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _default_registry_path() -> Path:
    # app/core/decision_engine/threshold_registry.py → parents[3] = chakraops package root
    repo = Path(__file__).resolve().parents[3]
    return repo / "config" / "threshold_registry.yaml"


def _normalize_key(key: str) -> str:
    return (key or "").strip()


def load_threshold_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and lightly validate the threshold registry YAML."""
    p = path or _default_registry_path()
    if not p.exists():
        raise ThresholdRegistryError(f"threshold_registry.yaml not found at {p}")
    import yaml

    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, Mapping):
        raise ThresholdRegistryError("threshold_registry.yaml root must be a mapping")
    profiles = data.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ThresholdRegistryError("threshold_registry.yaml must contain a 'profiles' mapping")

    for profile_name, keys in profiles.items():
        if not isinstance(keys, Mapping):
            raise ThresholdRegistryError(f"profile '{profile_name}' must be a mapping of keys")
        for key, meta in keys.items():
            if not isinstance(meta, Mapping):
                raise ThresholdRegistryError(f"{profile_name}.{key}: must be a mapping")
            source = str(meta.get("source") or "").strip().lower()
            if source not in ALLOWED_SOURCES:
                raise ThresholdRegistryError(
                    f"{profile_name}.{key}: source must be one of {sorted(ALLOWED_SOURCES)}"
                )
            evidence = meta.get("evidence_path")
            if source == "calibrated" and not evidence:
                raise ThresholdRegistryError(
                    f"{profile_name}.{key}: calibrated requires non-null evidence_path"
                )
    return dict(data)


def get_threshold_provenance(
    profile: str,
    key: str,
    *,
    path: Optional[Path] = None,
) -> ThresholdProvenance:
    """Return provenance for ``profile`` + dotted ``key``.

    ``custom`` inherits provenance from ``balanced`` (baseline before overrides).
    """
    data = load_threshold_registry(path)
    runtime_source = str(data.get("runtime_source") or "strategy_profiles.yaml")
    profiles = data["profiles"]
    name = (profile or "").strip().lower()
    if name == "custom":
        name = "balanced"
    if name not in profiles:
        raise ThresholdRegistryError(f"unknown profile '{profile}' in threshold registry")
    k = _normalize_key(key)
    meta = profiles[name].get(k)
    if meta is None:
        raise ThresholdRegistryError(f"unknown key '{key}' for profile '{profile}'")
    evidence = meta.get("evidence_path")
    return ThresholdProvenance(
        profile=(profile or "").strip().lower() or name,
        key=k,
        source=str(meta.get("source")).strip().lower(),
        evidence_path=str(evidence) if evidence else None,
        runtime_source=runtime_source,
    )


def list_threshold_keys(profile: str, *, path: Optional[Path] = None) -> Dict[str, dict]:
    """Return all provenance entries for a profile as plain dicts."""
    data = load_threshold_registry(path)
    name = (profile or "").strip().lower()
    lookup = "balanced" if name == "custom" else name
    profiles = data["profiles"]
    if lookup not in profiles:
        raise ThresholdRegistryError(f"unknown profile '{profile}' in threshold registry")
    runtime_source = str(data.get("runtime_source") or "strategy_profiles.yaml")
    out: Dict[str, dict] = {}
    for k, meta in profiles[lookup].items():
        out[k] = {
            "profile": name or lookup,
            "key": k,
            "source": str(meta.get("source")).strip().lower(),
            "evidence_path": meta.get("evidence_path"),
            "runtime_source": runtime_source,
        }
    return out
