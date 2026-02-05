/**
 * Phase 10: "Refresh now" — POST /api/ops/evaluate (DRY_RUN), poll job status, cooldown.
 */
import { useState, useCallback, useRef, useEffect } from "react";
import { apiGet, apiPost, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { pushSystemNotification } from "@/lib/notifications";
import { usePolling } from "@/context/PollingContext";

const JOB_POLL_MS = 2000;
const JOB_POLL_MAX_MS = 60_000;

export interface EvaluateTriggerState {
  loading: boolean;
  cooldownSeconds: number;
  message: string | null;
}

export function useEvaluateTrigger(): {
  trigger: () => Promise<void>;
  state: EvaluateTriggerState;
} {
  const [loading, setLoading] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const polling = usePolling();
  const cooldownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (cooldownIntervalRef.current) clearInterval(cooldownIntervalRef.current);
    };
  }, []);

  const trigger = useCallback(async () => {
    if (loading || cooldownSeconds > 0) return;
    setLoading(true);
    setMessage(null);
    try {
      const body = { reason: "MANUAL_REFRESH", scope: "ALL" as const };
      const token = (import.meta as unknown as { env?: { VITE_EVALUATE_TRIGGER_TOKEN?: string } }).env?.VITE_EVALUATE_TRIGGER_TOKEN;
      const headers = token ? { "X-Trigger-Token": token } : undefined;
      let data: { job_id?: string; accepted?: boolean; cooldown_seconds_remaining?: number };
      try {
        data = await apiPost(ENDPOINTS.evaluate, body, { timeoutMs: 15000, headers });
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.status === 403) {
            setMessage("Unauthorized");
            return;
          }
          if (e.status === 429) setMessage("Try again later");
          if (e.status === 404) {
            setMessage(`Refresh failed: 404 ${ENDPOINTS.evaluate}`);
            pushSystemNotification({
              source: "system",
              severity: "error",
              title: "Refresh failed",
              message: `POST ${ENDPOINTS.evaluate} returned 404. Check VITE_API_BASE_URL and backend.`,
            });
            return;
          }
        }
        throw e;
      }

      if (!data.accepted && data.cooldown_seconds_remaining != null) {
        setCooldownSeconds(data.cooldown_seconds_remaining);
        setMessage(`Try again in ${Math.ceil(data.cooldown_seconds_remaining / 60)} min`);
        if (cooldownIntervalRef.current) clearInterval(cooldownIntervalRef.current);
        const start = Date.now();
        cooldownIntervalRef.current = setInterval(() => {
          const left = data.cooldown_seconds_remaining! - Math.floor((Date.now() - start) / 1000);
          setCooldownSeconds(Math.max(0, left));
          if (left <= 0) {
            if (cooldownIntervalRef.current) clearInterval(cooldownIntervalRef.current);
            cooldownIntervalRef.current = null;
            setMessage(null);
          }
        }, 1000);
        return;
      }

      if (data.accepted && data.job_id) {
        pushSystemNotification({
          source: "system",
          severity: "info",
          title: "Refresh requested",
          message: "Evaluation job started. Views will update when complete.",
        });
        polling?.triggerRefetch?.();
        const jobId = data.job_id;
        const deadline = Date.now() + JOB_POLL_MAX_MS;
        const poll = async () => {
          while (Date.now() < deadline) {
            await new Promise((r) => setTimeout(r, JOB_POLL_MS));
            try {
              const status = await apiGet<{ state: string; error?: string }>(`${ENDPOINTS.evaluate}/${jobId}`);
              if (status?.state === "done") {
                polling?.triggerRefetch?.();
                setMessage("Done");
                setTimeout(() => setMessage(null), 3000);
                return;
              }
              if (status?.state === "failed") {
                setMessage(status?.error ?? "Evaluation failed");
                return;
              }
              if (status?.state === "not_found") {
                setMessage("Job not found");
                return;
              }
            } catch {
              // keep polling (API returns 200 for unknown job with state=not_found, so no 404)
            }
          }
          setMessage("Timeout");
        };
        void poll();
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        setMessage("Rate limited");
        return;
      }
      const msg = e instanceof ApiError
        ? `${e.status} ${ENDPOINTS.evaluate}${e.bodySnippet ? ` — ${e.bodySnippet.slice(0, 80)}` : ""}`
        : (e instanceof Error ? e.message : "Request failed");
      setMessage(msg);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Refresh failed",
        message: e instanceof ApiError
          ? `${ENDPOINTS.evaluate} returned ${e.status}. ${e.message}`
          : (e instanceof Error ? e.message : "Could not start evaluation"),
      });
    } finally {
      setLoading(false);
    }
  }, [loading, cooldownSeconds, polling]);

  return {
    trigger,
    state: { loading, cooldownSeconds, message },
  };
}
