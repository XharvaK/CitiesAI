"""Shared timing constants for export freshness and GUI polling."""

from __future__ import annotations

EXPORT_INTERVAL_SECONDS = 10
STALE_AFTER_SECONDS = 30
GUI_POLL_MS = EXPORT_INTERVAL_SECONDS * 1000
