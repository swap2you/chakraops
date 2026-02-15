/**
 * TanStack Query hooks for UI API endpoints.
 * Requires @tanstack/react-query.
 */

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";
import type {
  ArtifactListResponse,
  DecisionResponse,
  UniverseResponse,
  SymbolDiagnosticsResponseExtended,
  UiSystemHealthResponse,
  UiTrackedPositionsResponse,
} from "./types";
import type { DecisionMode } from "./types";

// =============================================================================
// Paths
// =============================================================================

function decisionFilesPath(mode: DecisionMode): string {
  return `/api/ui/decision/files?mode=${mode}`;
}

function decisionLatestPath(mode: DecisionMode): string {
  return `/api/ui/decision/latest?mode=${mode}`;
}

function decisionFilePath(filename: string, mode: DecisionMode): string {
  return `/api/ui/decision/file/${encodeURIComponent(filename)}?mode=${mode}`;
}

function universePath(): string {
  return `/api/ui/universe`;
}

function symbolDiagnosticsPath(symbol: string): string {
  return `/api/ui/symbol-diagnostics?symbol=${encodeURIComponent(symbol)}`;
}

function uiSystemHealthPath(): string {
  return `/api/ui/system-health`;
}

function uiTrackedPositionsPath(): string {
  return `/api/ui/positions/tracked`;
}

// =============================================================================
// Query keys
// =============================================================================

export const queryKeys = {
  artifactList: (mode: DecisionMode) => ["ui", "artifactList", mode] as const,
  decision: (mode: DecisionMode, filename?: string) =>
    filename
      ? (["ui", "decision", mode, filename] as const)
      : (["ui", "decision", mode, "latest"] as const),
  universe: () => ["ui", "universe"] as const,
  symbolDiagnostics: (symbol: string) =>
    ["ui", "symbolDiagnostics", symbol] as const,
  uiSystemHealth: () => ["ui", "systemHealth"] as const,
  uiTrackedPositions: () => ["ui", "positions", "tracked"] as const,
};

// =============================================================================
// Hooks
// =============================================================================

export function useArtifactList(mode: DecisionMode) {
  return useQuery({
    queryKey: queryKeys.artifactList(mode),
    queryFn: () => apiGet<ArtifactListResponse>(decisionFilesPath(mode)),
  });
}

export function useDecision(mode: DecisionMode, filename?: string) {
  const path =
    filename && filename !== "decision_latest.json"
      ? decisionFilePath(filename, mode)
      : decisionLatestPath(mode);
  return useQuery({
    queryKey: queryKeys.decision(mode, filename),
    queryFn: () => apiGet<DecisionResponse>(path),
  });
}

export function useUniverse() {
  return useQuery({
    queryKey: queryKeys.universe(),
    queryFn: () => apiGet<UniverseResponse>(universePath()),
  });
}

export function useSymbolDiagnostics(
  symbol: string,
  enabled = true
) {
  return useQuery({
    queryKey: queryKeys.symbolDiagnostics(symbol),
    queryFn: () =>
      apiGet<SymbolDiagnosticsResponseExtended>(symbolDiagnosticsPath(symbol)),
    enabled: enabled && symbol.trim().length > 0,
  });
}

export function useUiSystemHealth() {
  return useQuery({
    queryKey: queryKeys.uiSystemHealth(),
    queryFn: () => apiGet<UiSystemHealthResponse>(uiSystemHealthPath()),
  });
}

export function useUiTrackedPositions() {
  return useQuery({
    queryKey: queryKeys.uiTrackedPositions(),
    queryFn: () => apiGet<UiTrackedPositionsResponse>(uiTrackedPositionsPath()),
  });
}
