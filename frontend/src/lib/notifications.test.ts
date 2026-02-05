import { describe, it, expect } from "vitest";
import {
  loadNotificationState,
  markNotificationRead,
  markAllNotificationsRead,
  notificationsFromAlerts,
  groupNotificationsByTime,
  pushSystemNotificationItem,
  loadPendingSystemNotifications,
} from "./notifications";
import type { AlertsView } from "@/types/views";
import type { NotificationItem } from "./notifications";

describe("notifications", () => {
  it("loadNotificationState returns object with readIds array", () => {
    const state = loadNotificationState();
    expect(state).toHaveProperty("readIds");
    expect(Array.isArray(state.readIds)).toBe(true);
  });

  it("markNotificationRead does not throw when localStorage disabled", () => {
    const original = localStorage.setItem;
    localStorage.setItem = () => {
      throw new Error("disabled");
    };
    expect(() => markNotificationRead("id-1")).not.toThrow();
    localStorage.setItem = original;
  });

  it("markAllNotificationsRead does not throw when localStorage disabled", () => {
    const original = localStorage.setItem;
    localStorage.setItem = () => {
      throw new Error("disabled");
    };
    expect(() => markAllNotificationsRead(["id-1", "id-2"])).not.toThrow();
    localStorage.setItem = original;
  });

  it("notificationsFromAlerts builds list from AlertsView", () => {
    const alerts: AlertsView = {
      as_of: "2026-02-01T14:00:00Z",
      items: [{ code: "A", message: "Msg", symbol: "SPY" }],
    };
    const list = notificationsFromAlerts(alerts);
    expect(list).toHaveLength(1);
    expect(list[0].id).toContain("alert");
    expect(list[0].symbol).toBe("SPY");
  });

  it("groupNotificationsByTime returns groups", () => {
    const now = new Date().toISOString();
    const items: NotificationItem[] = [
      { id: "1", source: "alert", severity: "info", title: "A", message: "M", createdAt: now, actionable: true },
    ];
    const groups = groupNotificationsByTime(items);
    expect(groups.length).toBeGreaterThanOrEqual(1);
  });

  it("pushSystemNotificationItem does not add duplicate when same id already in pending (Phase 10 dedupe)", () => {
    const full: NotificationItem = {
      id: "dedupe-test-id",
      source: "system",
      severity: "info",
      title: "Test",
      message: "M",
      createdAt: new Date().toISOString(),
      actionable: false,
    };
    pushSystemNotificationItem(full);
    pushSystemNotificationItem(full);
    const pending = loadPendingSystemNotifications();
    const withId = pending.filter((p) => p.id === "dedupe-test-id");
    expect(withId).toHaveLength(1);
  });
});
