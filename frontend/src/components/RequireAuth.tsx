/**
 * AUTH-001 route guard: when backend auth is required, redirect unauthenticated
 * users to /login (preserving deep link). When disabled, render children.
 */
import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { fetchAuthStatus, fetchMe } from "@/api/auth";
import { ApiError } from "@/api/client";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const [state, setState] = useState<"loading" | "ok" | "login">("loading");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await fetchAuthStatus();
        if (!status.required) {
          if (!cancelled) setState("ok");
          return;
        }
        if (status.authenticated) {
          if (!cancelled) setState("ok");
          return;
        }
        // Confirm with /me (authoritative when required).
        try {
          await fetchMe();
          if (!cancelled) setState("ok");
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) {
            if (!cancelled) setState("login");
            return;
          }
          if (!cancelled) setState("login");
        }
      } catch {
        // Status unreachable → do not lock local UI.
        if (!cancelled) setState("ok");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  if (state === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 text-sm text-zinc-500 dark:bg-zinc-950">
        Loading…
      </div>
    );
  }
  if (state === "login") {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next || "/")}`} replace />;
  }
  return <>{children}</>;
}
