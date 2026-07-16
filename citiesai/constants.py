"""Shared timing constants for export freshness and GUI polling."""

from __future__ import annotations

EXPORT_INTERVAL_SECONDS = 10
STALE_AFTER_SECONDS = 30
HISTORY_MAX_POINTS = 500
WATCH_ALERT_COOLDOWN_SECONDS = 30 * 60
GUI_POLL_MS = EXPORT_INTERVAL_SECONDS * 1000
