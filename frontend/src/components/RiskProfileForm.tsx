/**
 * Phase 3: Risk profile editor — numeric thresholds, allowlist/denylist, toggles.
 */
import { useState, useEffect, useCallback } from "react";
import { apiGet, apiPut, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import type { RiskProfile } from "@/types/portfolio";
import { pushSystemNotification } from "@/lib/notifications";
import { Loader2, Save } from "lucide-react";

export function RiskProfileForm() {
  const [profile, setProfile] = useState<RiskProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProfile = useCallback(async () => {
    setError(null);
    try {
      const res = await apiGet<RiskProfile>(ENDPOINTS.portfolioRiskProfile);
      setProfile(res);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(msg);
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const updateField = (field: keyof RiskProfile, value: unknown) => {
    if (!profile) return;
    setProfile({ ...profile, [field]: value });
  };

  const handleSave = async () => {
    if (!profile) return;
    setSaving(true);
    try {
      await apiPut(ENDPOINTS.portfolioRiskProfilePut, profile);
      pushSystemNotification({
        source: "system",
        severity: "info",
        title: "Risk profile saved",
        message: "Your risk thresholds have been updated.",
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Save failed",
        message: msg,
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading risk profile...
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
        {error ?? "Failed to load risk profile"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">
            Max Capital Utilization %
          </label>
          <input
            type="number"
            min={0.05}
            max={1}
            step={0.05}
            value={profile.max_capital_utilization_pct}
            onChange={(e) =>
              updateField("max_capital_utilization_pct", parseFloat(e.target.value) || 0.35)
            }
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">
            Max Single Symbol Exposure %
          </label>
          <input
            type="number"
            min={0.01}
            max={0.5}
            step={0.01}
            value={profile.max_single_symbol_exposure_pct}
            onChange={(e) =>
              updateField("max_single_symbol_exposure_pct", parseFloat(e.target.value) || 0.10)
            }
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">
            Max Single Sector Exposure %
          </label>
          <input
            type="number"
            min={0.05}
            max={0.5}
            step={0.05}
            value={profile.max_single_sector_exposure_pct}
            onChange={(e) =>
              updateField("max_single_sector_exposure_pct", parseFloat(e.target.value) || 0.25)
            }
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">
            Max Open Positions
          </label>
          <input
            type="number"
            min={1}
            max={50}
            value={profile.max_open_positions}
            onChange={(e) =>
              updateField("max_open_positions", parseInt(e.target.value, 10) || 12)
            }
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">
            Max Positions Per Sector
          </label>
          <input
            type="number"
            min={1}
            max={20}
            value={profile.max_positions_per_sector}
            onChange={(e) =>
              updateField("max_positions_per_sector", parseInt(e.target.value, 10) || 4)
            }
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">
            Stop-Loss Cooldown (days, optional)
          </label>
          <input
            type="number"
            min={0}
            max={30}
            placeholder="Off"
            value={profile.stop_loss_cooldown_days ?? ""}
            onChange={(e) => {
              const v = e.target.value.trim();
              updateField("stop_loss_cooldown_days", v ? parseInt(v, 10) : null);
            }}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-muted-foreground mb-1">
          Allowlist Symbols (comma-separated)
        </label>
        <input
          type="text"
          placeholder="NVDA, AAPL"
          value={(profile.allowlist_symbols ?? []).join(", ")}
          onChange={(e) =>
            updateField(
              "allowlist_symbols",
              e.target.value
                .split(",")
                .map((s) => s.trim().toUpperCase())
                .filter(Boolean)
            )
          }
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-muted-foreground mb-1">
          Denylist Symbols (comma-separated)
        </label>
        <input
          type="text"
          placeholder="TSLA"
          value={(profile.denylist_symbols ?? []).join(", ")}
          onChange={(e) =>
            updateField(
              "denylist_symbols",
              e.target.value
                .split(",")
                .map((s) => s.trim().toUpperCase())
                .filter(Boolean)
            )
          }
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
        />
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {saving ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Save className="h-4 w-4" />
        )}
        Save Risk Profile
      </button>
    </div>
  );
}
