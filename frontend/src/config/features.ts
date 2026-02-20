/**
 * R22.3: Wheel page visibility and labeling (PO decision).
 * VITE_WHEEL_PAGE_MODE:
 * - admin (default): Show Wheel in nav, labeled as Admin/Recovery.
 * - advanced: Show Wheel only when user enables "Show advanced" in UI.
 * - hidden: Remove Wheel from nav and routes (redirect /wheel → /).
 */
export type WheelPageMode = "admin" | "advanced" | "hidden";

const MODE = (import.meta.env.VITE_WHEEL_PAGE_MODE ?? "admin") as string;

export function getWheelPageMode(): WheelPageMode {
  if (MODE === "advanced" || MODE === "hidden") return MODE;
  return "admin";
}

const STORAGE_KEY = "chakraops_show_advanced";

export function getShowAdvanced(): boolean {
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function setShowAdvanced(value: boolean): void {
  try {
    if (value) globalThis.localStorage?.setItem(STORAGE_KEY, "true");
    else globalThis.localStorage?.setItem(STORAGE_KEY, "false");
  } catch {
    /* no-op */
  }
}

/** Wheel link visible in nav: admin always; advanced only when showAdvanced; hidden never. */
export function isWheelLinkVisible(): boolean {
  const mode = getWheelPageMode();
  if (mode === "hidden") return false;
  if (mode === "advanced") return getShowAdvanced();
  return true;
}
