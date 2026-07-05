from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from .config import load_config
from .dashboard import extract_headline_metrics
from .snapshot import load_snapshot_safe, snapshot_meta

_HISTORY_KEYS = (
    "population",
    "treasury",
    "income",
    "expense",
    "wellbeing",
    "health",
    "congestion_percent",
    "unemployment_percent",
)


@dataclass(frozen=True)
class HistoryPoint:
    timestamp: float
    exported_at_utc: str | None
    metrics: dict[str, Any]


class SnapshotHistory:
    def __init__(self, *, max_points: int = 120) -> None:
        self._max_points = max_points
        self._points: deque[HistoryPoint] = deque(maxlen=max_points)
        self._last_mtime: float | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="snapshot-history", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.refresh()
            except OSError:
                pass
            self._stop.wait(5.0)

    def refresh(self) -> bool:
        cfg = load_config()
        path = cfg.resolved_export_path()
        if not path.is_file():
            return False
        mtime = path.stat().st_mtime
        with self._lock:
            if self._last_mtime is not None and mtime == self._last_mtime:
                return False
            self._last_mtime = mtime
        snapshot, _ = load_snapshot_safe(path)
        if snapshot is None:
            return False
        meta = snapshot_meta(snapshot, path=path)
        headline = extract_headline_metrics(snapshot, meta)
        point = HistoryPoint(
            timestamp=time.time(),
            exported_at_utc=meta.exported_at_utc,
            metrics={key: headline.get(key) for key in _HISTORY_KEYS},
        )
        with self._lock:
            if self._points and self._points[-1].exported_at_utc == point.exported_at_utc:
                self._points[-1] = point
            else:
                self._points.append(point)
        return True

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            points = list(self._points)
        series: dict[str, list[Any]] = {key: [] for key in _HISTORY_KEYS}
        timestamps: list[float] = []
        for point in points:
            timestamps.append(point.timestamp)
            for key in _HISTORY_KEYS:
                series[key].append(point.metrics.get(key))
        deltas: dict[str, Any] = {}
        if len(points) >= 2:
            prev, curr = points[-2].metrics, points[-1].metrics
            for key in _HISTORY_KEYS:
                a, b = prev.get(key), curr.get(key)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    deltas[key] = b - a
        return {
            "count": len(points),
            "timestamps": timestamps,
            "series": series,
            "deltas": deltas,
            "latest_exported_at_utc": points[-1].exported_at_utc if points else None,
        }


_history: SnapshotHistory | None = None


def get_history() -> SnapshotHistory:
    global _history
    if _history is None:
        _history = SnapshotHistory()
        _history.start()
    return _history
