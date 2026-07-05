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
from .constants import EXPORT_INTERVAL_SECONDS, HISTORY_MAX_POINTS, WATCH_ALERT_COOLDOWN_SECONDS
from .dashboard import extract_headline_metrics
from .snapshot import load_snapshot_safe, snapshot_meta

_HISTORY_METRIC_KEYS = (
    "population",
    "treasury",
    "income",
    "expense",
    "wellbeing",
    "health",
    "crime_rate",
    "congestion_percent",
    "unemployment_percent",
    "electricity_fulfillment_percent",
    "water_fulfillment_percent",
    "sewage_fulfillment_percent",
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

CREATE TABLE IF NOT EXISTS tracked_issues (
    id INTEGER PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id),
    issue_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    resolved_at REAL,
    session_count INTEGER NOT NULL DEFAULT 1,
    UNIQUE(city_id, issue_id)
);

CREATE INDEX IF NOT EXISTS idx_tracked_issues_city ON tracked_issues(city_id, resolved_at);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id),
    alert_id TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    created_at REAL NOT NULL,
    read_at REAL
);

CREATE INDEX IF NOT EXISTS idx_notifications_city_time ON notifications(city_id, created_at DESC);
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

    def sync_tracked_issues(self, city_name: str, issues: list[dict[str, Any]]) -> None:
        now = datetime.now(UTC).timestamp()
        city_issues = {
            str(issue.get("id")): issue
            for issue in issues
            if issue.get("kind") == "city" and issue.get("id")
        }
        active_ids = set(city_issues)
        with self._lock, self._connect() as conn:
            city_id = self._city_id(conn, city_name)
            rows = conn.execute(
                """
                SELECT issue_id FROM tracked_issues
                WHERE city_id = ? AND resolved_at IS NULL
                """,
                (city_id,),
            ).fetchall()
            open_ids = {str(row["issue_id"]) for row in rows}
            for issue_id in open_ids - active_ids:
                conn.execute(
                    """
                    UPDATE tracked_issues
                    SET resolved_at = ?, last_seen = ?
                    WHERE city_id = ? AND issue_id = ?
                    """,
                    (now, now, city_id, issue_id),
                )
            for issue_id, issue in city_issues.items():
                if issue_id in open_ids:
                    conn.execute(
                        """
                        UPDATE tracked_issues
                        SET last_seen = ?, severity = ?, title = ?, detail = ?
                        WHERE city_id = ? AND issue_id = ? AND resolved_at IS NULL
                        """,
                        (
                            now,
                            str(issue.get("severity") or "info"),
                            str(issue.get("title") or issue_id),
                            str(issue.get("detail") or ""),
                            city_id,
                            issue_id,
                        ),
                    )
                    continue
                conn.execute(
                    """
                    INSERT INTO tracked_issues(
                        city_id, issue_id, severity, title, detail,
                        first_seen, last_seen, session_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        city_id,
                        issue_id,
                        str(issue.get("severity") or "info"),
                        str(issue.get("title") or issue_id),
                        str(issue.get("detail") or ""),
                        now,
                        now,
                    ),
                )
            conn.commit()

    def enrich_issues_with_lifecycle(
        self,
        issues: list[dict[str, Any]],
        *,
        city_name: str | None = None,
    ) -> list[dict[str, Any]]:
        name = city_name
        if not name:
            return issues
        with self._connect() as conn:
            city_row = conn.execute("SELECT id FROM cities WHERE name = ?", (name,)).fetchone()
            if not city_row:
                return issues
            rows = conn.execute(
                """
                SELECT issue_id, first_seen, last_seen, resolved_at, session_count
                FROM tracked_issues WHERE city_id = ?
                """,
                (int(city_row["id"]),),
            ).fetchall()
        by_id = {str(row["issue_id"]): dict(row) for row in rows}
        enriched: list[dict[str, Any]] = []
        for issue in issues:
            row = dict(issue)
            lifecycle = by_id.get(str(issue.get("id") or ""))
            if lifecycle and lifecycle.get("resolved_at") is None:
                row["first_seen"] = lifecycle["first_seen"]
                row["last_seen"] = lifecycle["last_seen"]
                row["session_count"] = int(lifecycle.get("session_count") or 1)
            enriched.append(row)
        return enriched

    def get_resolved_since_last_session(
        self,
        city_name: str | None = None,
        *,
        export_path: Path | None = None,
        history: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        hist = history or self.get_history(city_name, export_path=export_path)
        name = str(hist.get("city_name") or city_name or "")
        points = hist.get("points") or []
        boundary = _session_boundary_index(points)
        if boundary is None:
            since_ts = 0.0
        else:
            boundary_ts = _parse_exported_at(str(points[boundary]["exported_at_utc"]))
            since_ts = boundary_ts.timestamp() if boundary_ts else 0.0
        with self._connect() as conn:
            city_row = conn.execute("SELECT id FROM cities WHERE name = ?", (name,)).fetchone()
            if not city_row:
                return []
            rows = conn.execute(
                """
                SELECT issue_id, title, resolved_at
                FROM tracked_issues
                WHERE city_id = ? AND resolved_at IS NOT NULL AND resolved_at >= ?
                ORDER BY resolved_at DESC
                """,
                (int(city_row["id"]), since_ts),
            ).fetchall()
        return [
            {
                "id": str(row["issue_id"]),
                "title": str(row["title"]),
                "resolved_at": float(row["resolved_at"]),
            }
            for row in rows
        ]

    def get_resolved_history(self, city_name: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            city_row = conn.execute("SELECT id FROM cities WHERE name = ?", (city_name,)).fetchone()
            if not city_row:
                return []
            rows = conn.execute(
                """
                SELECT issue_id, title, first_seen, resolved_at
                FROM tracked_issues
                WHERE city_id = ? AND resolved_at IS NOT NULL
                ORDER BY resolved_at DESC LIMIT ?
                """,
                (int(city_row["id"]), limit),
            ).fetchall()
        return [
            {
                "id": str(row["issue_id"]),
                "title": str(row["title"]),
                "first_seen": float(row["first_seen"]),
                "resolved_at": float(row["resolved_at"]),
            }
            for row in rows
        ]

    def record_notification(
        self,
        city_name: str,
        *,
        alert_id: str,
        title: str,
        message: str,
        severity: str = "info",
    ) -> None:
        now = datetime.now(UTC).timestamp()
        with self._lock, self._connect() as conn:
            city_id = self._city_id(conn, city_name)
            existing = conn.execute(
                """
                SELECT id FROM notifications
                WHERE city_id = ? AND alert_id = ? AND created_at > ?
                """,
                (city_id, alert_id, now - WATCH_ALERT_COOLDOWN_SECONDS),
            ).fetchone()
            if existing:
                return
            conn.execute(
                """
                INSERT INTO notifications(city_id, alert_id, title, message, severity, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (city_id, alert_id, title, message[:500], severity, now),
            )
            conn.commit()

    def list_notifications(
        self,
        city_name: str,
        *,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT id, alert_id, title, message, severity, created_at, read_at
            FROM notifications WHERE city_id = (
                SELECT id FROM cities WHERE name = ?
            )
        """
        if unread_only:
            query += " AND read_at IS NULL"
        query += " ORDER BY created_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, (city_name, limit)).fetchall()
        return [
            {
                "id": int(row["id"]),
                "alert_id": str(row["alert_id"]),
                "title": str(row["title"]),
                "message": str(row["message"]),
                "severity": str(row["severity"]),
                "created_at": float(row["created_at"]),
                "read_at": float(row["read_at"]) if row["read_at"] is not None else None,
                "unread": row["read_at"] is None,
            }
            for row in rows
        ]

    def mark_notifications_read(self, city_name: str, notification_ids: list[int] | None = None) -> int:
        now = datetime.now(UTC).timestamp()
        with self._lock, self._connect() as conn:
            city_row = conn.execute("SELECT id FROM cities WHERE name = ?", (city_name,)).fetchone()
            if not city_row:
                return 0
            city_id = int(city_row["id"])
            if notification_ids:
                placeholders = ",".join("?" for _ in notification_ids)
                cursor = conn.execute(
                    f"""
                    UPDATE notifications SET read_at = ?
                    WHERE city_id = ? AND id IN ({placeholders}) AND read_at IS NULL
                    """,
                    (now, city_id, *notification_ids),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE notifications SET read_at = ?
                    WHERE city_id = ? AND read_at IS NULL
                    """,
                    (now, city_id),
                )
            conn.commit()
            return int(cursor.rowcount)

    def unread_notification_count(self, city_name: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM notifications
                WHERE city_id = (SELECT id FROM cities WHERE name = ?) AND read_at IS NULL
                """,
                (city_name,),
            ).fetchone()
        return int(row["count"]) if row else 0

    def get_grade_history(self, city_name: str, *, limit: int = 100) -> dict[str, Any]:
        with self._connect() as conn:
            city_row = conn.execute("SELECT id FROM cities WHERE name = ?", (city_name,)).fetchone()
            if not city_row:
                return {"city_name": city_name, "points": []}
            rows = conn.execute(
                """
                SELECT exported_at_utc, scores_json FROM report_scores
                WHERE city_id = ? ORDER BY exported_at_utc DESC LIMIT ?
                """,
                (int(city_row["id"]), limit),
            ).fetchall()
        points: list[dict[str, Any]] = []
        for row in reversed(rows):
            try:
                scores = json.loads(str(row["scores_json"]))
            except json.JSONDecodeError:
                continue
            if not isinstance(scores, dict):
                continue
            values = [
                float(row["score"])
                for row in scores.values()
                if isinstance(row, dict) and isinstance(row.get("score"), (int, float))
            ]
            overall_score = round(sum(values) / len(values), 1) if values else None
            overall_grade = None
            if overall_score is not None:
                if overall_score >= 90:
                    overall_grade = "A"
                elif overall_score >= 80:
                    overall_grade = "B"
                elif overall_score >= 70:
                    overall_grade = "C"
                elif overall_score >= 60:
                    overall_grade = "D"
                else:
                    overall_grade = "F"
            points.append(
                {
                    "exported_at_utc": str(row["exported_at_utc"]),
                    "overall_grade": overall_grade,
                    "overall_score": overall_score,
                    "domains": scores,
                }
            )
        return {"city_name": city_name, "points": points}

    def record_session_end(self, city_name: str, metrics: dict[str, Any]) -> None:
        del metrics
        with self._lock, self._connect() as conn:
            city_row = conn.execute("SELECT id FROM cities WHERE name = ?", (city_name,)).fetchone()
            if not city_row:
                return
            city_id = int(city_row["id"])
            conn.execute(
                """
                UPDATE tracked_issues
                SET session_count = session_count + 1
                WHERE city_id = ? AND resolved_at IS NULL
                """,
                (city_id,),
            )
            conn.commit()

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
            "resolved": self.get_resolved_since_last_session(name, history=hist),
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
