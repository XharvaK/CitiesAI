"""Persistent city history from CS2 Data Export snapshots."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .city_name import resolve_city_display_name
from .config import config_dir, load_config
from .constants import EXPORT_INTERVAL_SECONDS, HISTORY_MAX_POINTS
from .dashboard import extract_headline_metrics
from .snapshot import load_snapshot_safe, snapshot_meta

_HISTORY_METRIC_KEYS = (
    "population",
    "treasury",
    "income",
    "expense",
    "wellbeing",
    "health",
    "congestion_percent",
    "unemployment_percent",
    "homeless",
    "moving_away",
    "treasury_net_per_hour",
    "population_change_per_hour",
)

SESSION_GAP_SECONDS = 30 * 60
SYNC_THROTTLE_SECONDS = float(EXPORT_INTERVAL_SECONDS)
METRICS_SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id),
    exported_at_utc TEXT NOT NULL,
    source_path TEXT,
    metrics_json TEXT NOT NULL,
    ingested_at REAL NOT NULL,
    UNIQUE(city_id, exported_at_utc)
);

CREATE TABLE IF NOT EXISTS ingested_files (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    ingested_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id),
    ended_at REAL NOT NULL,
    metrics_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_scores (
    id INTEGER PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id),
    exported_at_utc TEXT NOT NULL,
    scores_json TEXT NOT NULL,
    ingested_at REAL NOT NULL,
    UNIQUE(city_id, exported_at_utc)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_city_time ON snapshots(city_id, exported_at_utc);
"""


@dataclass(frozen=True)
class HistorianPoint:
    exported_at_utc: str
    metrics: dict[str, Any]


def _parse_exported_at(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        return None


def _session_boundary_index(points: list[dict[str, Any]], *, gap_seconds: float = SESSION_GAP_SECONDS) -> int | None:
    """Return index of last point in the previous session, or None if only one session."""
    if len(points) < 2:
        return None
    for index in range(len(points) - 1, 0, -1):
        curr_ts = _parse_exported_at(str(points[index]["exported_at_utc"]))
        prev_ts = _parse_exported_at(str(points[index - 1]["exported_at_utc"]))
        if curr_ts and prev_ts and (curr_ts - prev_ts).total_seconds() > gap_seconds:
            return index - 1
    return None


class CityHistorian:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or (config_dir() / "historian.db")
        self._lock = threading.Lock()
        self._last_sync_at: float = 0.0
        self._pending_force_sync = False
        self._ensure_schema()
        self._migrate_metrics_schema()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _migrate_metrics_schema(self) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'metrics_schema_version'",
            ).fetchone()
            stored = int(row["value"]) if row else 1
            if stored >= METRICS_SCHEMA_VERSION:
                return
            conn.execute("DELETE FROM ingested_files")
            conn.execute(
                """
                INSERT INTO meta(key, value) VALUES ('metrics_schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(METRICS_SCHEMA_VERSION),),
            )
            conn.commit()
            self._pending_force_sync = True

    def _city_id(self, conn: sqlite3.Connection, name: str) -> int:
        conn.execute("INSERT OR IGNORE INTO cities(name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM cities WHERE name = ?", (name,)).fetchone()
        assert row is not None
        return int(row["id"])

    def _load_ingested_mtimes(self, conn: sqlite3.Connection) -> dict[str, float]:
        rows = conn.execute("SELECT path, mtime FROM ingested_files").fetchall()
        return {str(row["path"]): float(row["mtime"]) for row in rows}

    def _ingest_file(
        self,
        conn: sqlite3.Connection,
        path: Path,
        *,
        ingested_mtimes: dict[str, float],
    ) -> bool:
        if not path.is_file():
            return False
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return False

        path_key = str(path)
        if ingested_mtimes.get(path_key) == mtime:
            return False

        snapshot, _ = load_snapshot_safe(path)
        if snapshot is None:
            return False

        meta = snapshot_meta(snapshot, path=path)
        city_name = resolve_city_display_name(snapshot, meta)
        exported_at = meta.exported_at_utc
        if not exported_at:
            return False

        metrics = extract_headline_metrics(snapshot, meta)
        payload = {key: metrics.get(key) for key in _HISTORY_METRIC_KEYS}
        city_id = self._city_id(conn, city_name)
        now = datetime.now(UTC).timestamp()
        conn.execute(
            """
            INSERT INTO snapshots(city_id, exported_at_utc, source_path, metrics_json, ingested_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(city_id, exported_at_utc) DO UPDATE SET
                source_path = excluded.source_path,
                metrics_json = excluded.metrics_json,
                ingested_at = excluded.ingested_at
            """,
            (city_id, exported_at, path_key, json.dumps(payload), now),
        )
        conn.execute(
            """
            INSERT INTO ingested_files(path, mtime, ingested_at) VALUES (?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET mtime = excluded.mtime, ingested_at = excluded.ingested_at
            """,
            (path_key, mtime, now),
        )
        ingested_mtimes[path_key] = mtime
        return True

    def sync(self, export_path: Path | None = None, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._pending_force_sync:
                force = True
                self._pending_force_sync = False
            now = time.time()
            if not force and now - self._last_sync_at < SYNC_THROTTLE_SECONDS:
                return {"ingested": 0, "db_path": str(self._db_path), "skipped": True}

            cfg_path = (export_path or load_config().resolved_export_path()).expanduser()
            ingested = 0
            with self._connect() as conn:
                ingested_mtimes = self._load_ingested_mtimes(conn)
                if cfg_path.is_file():
                    if self._ingest_file(conn, cfg_path, ingested_mtimes=ingested_mtimes):
                        ingested += 1
                snap_dir = cfg_path.parent / "snapshots"
                if snap_dir.is_dir():
                    for path in sorted(snap_dir.glob("*.json")):
                        if self._ingest_file(conn, path, ingested_mtimes=ingested_mtimes):
                            ingested += 1
                conn.commit()
            self._last_sync_at = now
            return {"ingested": ingested, "db_path": str(self._db_path), "skipped": False}

    def _resolve_city_name(self, snapshot: dict[str, Any] | None, export_path: Path) -> str:
        if snapshot:
            meta = snapshot_meta(snapshot, path=export_path)
            return resolve_city_display_name(snapshot, meta)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name FROM cities ORDER BY id DESC LIMIT 1",
            ).fetchone()
        return str(row["name"]) if row else "Unknown City"

    def get_history(
        self,
        city_name: str | None = None,
        *,
        limit: int = HISTORY_MAX_POINTS,
        export_path: Path | None = None,
    ) -> dict[str, Any]:
        path = (export_path or load_config().resolved_export_path()).expanduser()
        snapshot, _ = load_snapshot_safe(path) if path.is_file() else (None, None)
        name = city_name or self._resolve_city_name(snapshot, path)

        with self._connect() as conn:
            city_row = conn.execute("SELECT id FROM cities WHERE name = ?", (name,)).fetchone()
            if not city_row:
                return {"city_name": name, "count": 0, "points": [], "series": {}, "timestamps": []}
            rows = conn.execute(
                """
                SELECT exported_at_utc, metrics_json FROM snapshots
                WHERE city_id = ? ORDER BY exported_at_utc DESC LIMIT ?
                """,
                (int(city_row["id"]), limit),
            ).fetchall()

        points: list[dict[str, Any]] = []
        series: dict[str, list[Any]] = {key: [] for key in _HISTORY_METRIC_KEYS}
        timestamps: list[str] = []
        for row in reversed(rows):
            metrics = json.loads(row["metrics_json"])
            points.append({"exported_at_utc": row["exported_at_utc"], "metrics": metrics})
            timestamps.append(row["exported_at_utc"])
            for key in _HISTORY_METRIC_KEYS:
                series[key].append(metrics.get(key))

        deltas: dict[str, Any] = {}
        if len(points) >= 2:
            prev, curr = points[-2]["metrics"], points[-1]["metrics"]
            for key in _HISTORY_METRIC_KEYS:
                a, b = prev.get(key), curr.get(key)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    deltas[key] = b - a

        return {
            "city_name": name,
            "count": len(points),
            "timestamps": timestamps,
            "points": points,
            "series": series,
            "deltas": deltas,
        }

    def record_session_end(self, city_name: str, metrics: dict[str, Any]) -> None:
        """Reserved for future session summaries; digest uses snapshot points."""
        del city_name, metrics

    def save_report_scores(
        self,
        city_name: str,
        exported_at_utc: str,
        domain_scores: dict[str, dict[str, Any]],
    ) -> None:
        with self._lock, self._connect() as conn:
            city_id = self._city_id(conn, city_name)
            conn.execute(
                """
                INSERT INTO report_scores(city_id, exported_at_utc, scores_json, ingested_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(city_id, exported_at_utc) DO UPDATE SET
                    scores_json = excluded.scores_json,
                    ingested_at = excluded.ingested_at
                """,
                (
                    city_id,
                    exported_at_utc,
                    json.dumps(domain_scores),
                    datetime.now(UTC).timestamp(),
                ),
            )
            conn.commit()

    def report_scores_at(self, city_name: str, exported_at_utc: str) -> dict[str, dict[str, Any]] | None:
        with self._connect() as conn:
            city_row = conn.execute("SELECT id FROM cities WHERE name = ?", (city_name,)).fetchone()
            if not city_row:
                return None
            row = conn.execute(
                """
                SELECT scores_json FROM report_scores
                WHERE city_id = ? AND exported_at_utc = ?
                """,
                (int(city_row["id"]), exported_at_utc),
            ).fetchone()
            if not row:
                return None
            try:
                return json.loads(str(row["scores_json"]))
            except json.JSONDecodeError:
                return None

    def previous_session_report_scores(
        self,
        city_name: str,
        *,
        history: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]] | None:
        points = (history or {}).get("points") or []
        if len(points) < 2:
            return None
        boundary = _session_boundary_index(points)
        if boundary is None:
            return None
        ref_point = points[boundary]
        exported_at = str(ref_point["exported_at_utc"])
        with self._connect() as conn:
            city_row = conn.execute("SELECT id FROM cities WHERE name = ?", (city_name,)).fetchone()
            if not city_row:
                return None
            row = conn.execute(
                """
                SELECT scores_json FROM report_scores
                WHERE city_id = ? AND exported_at_utc <= ?
                ORDER BY exported_at_utc DESC LIMIT 1
                """,
                (int(city_row["id"]), exported_at),
            ).fetchone()
        if not row:
            return None
        data = json.loads(row["scores_json"])
        return data if isinstance(data, dict) else None

    def session_digest(
        self,
        city_name: str | None = None,
        *,
        export_path: Path | None = None,
        history: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        hist = history or self.get_history(city_name, limit=HISTORY_MAX_POINTS, export_path=export_path)
        if hist["count"] < 1:
            return {"city_name": hist["city_name"], "has_changes": False, "summary": []}

        name = hist["city_name"]
        points = hist["points"]
        current = points[-1]["metrics"]
        boundary = _session_boundary_index(points)

        if boundary is None:
            return {"city_name": name, "has_changes": False, "summary": [], "current": current}

        previous = points[boundary]["metrics"]
        summary: list[str] = []
        labels = {
            "population": "Population",
            "treasury": "Treasury",
            "wellbeing": "Wellbeing",
            "health": "Health",
            "homeless": "Homeless",
            "unemployment_percent": "Unemployment",
        }
        for key, label in labels.items():
            a, b = previous.get(key), current.get(key)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a != b:
                delta = b - a
                if key == "treasury":
                    summary.append(f"{label}: {delta:+,} (now {b:,.0f})")
                elif key in ("wellbeing", "health", "unemployment_percent"):
                    summary.append(f"{label}: {delta:+.0f} (now {b:.0f})")
                else:
                    summary.append(f"{label}: {delta:+,} (now {b:,.0f})")

        return {
            "city_name": name,
            "has_changes": bool(summary),
            "summary": summary,
            "previous": previous,
            "current": current,
            "session_boundary": points[boundary]["exported_at_utc"],
        }

    def detect_anomalies(
        self,
        city_name: str | None = None,
        *,
        window: int = 20,
        history: dict[str, Any] | None = None,
        export_path: Path | None = None,
    ) -> list[dict[str, Any]]:
        hist = history or self.get_history(city_name, limit=window, export_path=export_path)
        points = hist["points"]
        if len(points) < 5:
            return []

        anomalies: list[dict[str, Any]] = []
        checks = [
            ("homeless", "Homeless spike", "warn", 50),
            ("treasury", "Treasury drop", "warn", None),
            ("wellbeing", "Wellbeing decline", "info", 5),
            ("health", "Health decline", "warn", 5),
        ]
        for key, title, severity, min_delta in checks:
            values = [
                p["metrics"].get(key)
                for p in points
                if isinstance(p["metrics"].get(key), (int, float))
            ]
            if len(values) < 5:
                continue
            recent = values[-1]
            baseline = sum(values[:-1]) / len(values[:-1])
            delta = recent - baseline
            threshold = min_delta if min_delta is not None else abs(baseline) * 0.15 + 1
            if key in ("wellbeing", "health") and delta < -threshold:
                anomalies.append(
                    {
                        "id": f"anomaly_{key}",
                        "severity": severity,
                        "title": title,
                        "detail": f"{key} fell from avg {baseline:.1f} to {recent:.1f}",
                        "ask_prompt": f"Why did {key} drop in my city?",
                    }
                )
            elif key == "homeless" and delta > threshold:
                anomalies.append(
                    {
                        "id": f"anomaly_{key}",
                        "severity": severity,
                        "title": title,
                        "detail": f"Homeless rose from avg {baseline:.0f} to {recent:.0f}",
                        "ask_prompt": "How do I reduce homelessness?",
                    }
                )
            elif key == "treasury" and delta < -threshold:
                anomalies.append(
                    {
                        "id": f"anomaly_{key}",
                        "severity": severity,
                        "title": title,
                        "detail": f"Treasury dropped from avg {baseline:,.0f} to {recent:,.0f}",
                        "ask_prompt": "How do I stop losing money?",
                    }
                )
        return anomalies


_historian: CityHistorian | None = None


def get_historian() -> CityHistorian:
    global _historian
    if _historian is None:
        _historian = CityHistorian()
    return _historian
