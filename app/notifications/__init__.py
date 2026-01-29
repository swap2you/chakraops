"""Notifications module for Phase 7 decision alerts."""

from app.notifications.slack_notifier import send_decision_alert

__all__ = ["send_decision_alert"]
