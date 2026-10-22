"""Local SQLite store: watch history and favorites (offline-first).

Keeps a local SQLite database plus optional remote sync when the user
logs in (catalog.get_remote_history / catalog.put_remote_history,
catalog.get_collect / catalog.toggle_collect).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Optional

from . import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    video_id    TEXT NOT NULL,
    episode_id  TEXT NOT NULL DEFAULT '',
    position_ms INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    updated_at  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (video_id, episode_id)
);
CREATE TABLE IF NOT EXISTS history_meta (
    video_id    TEXT PRIMARY KEY,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS favorites (
    video_id    TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    updated_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
"""


class LocalDB:
    def __init__(self) -> None:
        self._db = sqlite3.connect(str(paths.db_path()), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._migrate()
            self._db.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the first dev schema versions."""
        cols = {r["name"] for r in self._db.execute("PRAGMA table_info(history)")}
        for col, decl in (
            ("position_ms", "INTEGER NOT NULL DEFAULT 0"),
            ("duration_ms", "INTEGER NOT NULL DEFAULT 0"),
            ("updated_at", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if col not in cols:
                self._db.execute(f"ALTER TABLE history ADD COLUMN {col} {decl}")

    # ------------------------------------------------------------- history
    def put_history(self, video: dict, episode_id: str, episode_title: str,
                    position_ms: int, duration_ms: int) -> None:
        vid = str(video.get("id", ""))
        if not vid:
            return
        now = int(time.time() * 1000)
        meta = dict(video)
        meta.update({
            "episode_id": episode_id,
            "episode_title": episode_title,
            "position_ms": position_ms,
            "duration_ms": duration_ms,
            "updated_at": now,
        })
        with self._lock:
            self._db.execute(
                "INSERT INTO history (video_id, episode_id, position_ms, duration_ms, updated_at)"
                " VALUES (?,?,?,?,?)"
                " ON CONFLICT(video_id, episode_id) DO UPDATE SET"
                " position_ms=excluded.position_ms, duration_ms=excluded.duration_ms,"
                " updated_at=excluded.updated_at",
                (vid, episode_id, position_ms, duration_ms, now),
            )
            self._db.execute(
                "INSERT INTO history_meta (video_id, payload) VALUES (?,?)"
                " ON CONFLICT(video_id) DO UPDATE SET payload=excluded.payload",
                (vid, json.dumps(meta, ensure_ascii=False)),
            )
            self._db.commit()

    def list_history(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT h.video_id, h.episode_id, h.position_ms, h.duration_ms, h.updated_at,"
                " m.payload FROM history h JOIN history_meta m ON h.video_id = m.video_id"
                " ORDER BY h.updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            try:
                item = json.loads(r["payload"])
            except json.JSONDecodeError:
                item = {}
            item.update({
                "episode_id": r["episode_id"],
                "position_ms": r["position_ms"],
                "duration_ms": r["duration_ms"],
                "updated_at": r["updated_at"],
            })
            out.append(item)
        return out

    def clear_history(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM history")
            self._db.execute("DELETE FROM history_meta")
            self._db.commit()

    # ------------------------------------------------------------ favorites
    def put_favorite(self, video: dict) -> None:
        vid = str(video.get("id", ""))
        if not vid:
            return
        with self._lock:
            self._db.execute(
                "INSERT INTO favorites (video_id, payload, updated_at) VALUES (?,?,?)"
                " ON CONFLICT(video_id) DO UPDATE SET payload=excluded.payload,"
                " updated_at=excluded.updated_at",
                (vid, json.dumps(video, ensure_ascii=False), int(time.time() * 1000)),
            )
            self._db.commit()

    def remove_favorite(self, video_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM favorites WHERE video_id=?", (video_id,))
            self._db.commit()

    def is_favorite(self, video_id: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM favorites WHERE video_id=?", (video_id,)
            ).fetchone()
        return row is not None

    def list_favorites(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT payload FROM favorites ORDER BY updated_at DESC"
            ).fetchall()
        out = []
        for r in rows:
            try:
                out.append(json.loads(r["payload"]))
            except json.JSONDecodeError:
                continue
        return out

    # ------------------------------------------------------------------ kv
    def kv_get(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def kv_set(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO kv (key, value) VALUES (?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._db.commit()
