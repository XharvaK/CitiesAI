"""Shared timing constants for export freshness and GUI polling."""

from __future__ import annotations

EXPORT_INTERVAL_SECONDS = 5
STALE_AFTER_SECONDS = 15
HISTORY_MAX_POINTS = 1000
WATCH_ALERT_COOLDOWN_SECONDS = 30 * 60
GUI_POLL_MS = EXPORT_INTERVAL_SECONDS * 1000
