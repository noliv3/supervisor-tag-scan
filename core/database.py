from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class ScannerDB:
    def __init__(self, db_path: str = "scanner.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS files (
                        hash TEXT PRIMARY KEY,
                        path TEXT UNIQUE,
                        flags_done INTEGER DEFAULT 0,
                        meta_json TEXT,
                        nsfw_score FLOAT,
                        face_bbox_json TEXT,
                        vector_blob BLOB,
                        last_scanned DATETIME
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tags (
                        id INTEGER PRIMARY KEY,
                        name TEXT UNIQUE,
                        global_count INTEGER
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_tags (
                        file_hash TEXT,
                        tag_id INTEGER,
                        confidence FLOAT
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tag_trends (
                        date TEXT,
                        tag_id INTEGER,
                        day_count INTEGER,
                        PRIMARY KEY (date, tag_id)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tokens (
                        token TEXT PRIMARY KEY,
                        mail TEXT,
                        webseite TEXT,
                        last_used DATETIME
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS legacy_stats (
                        id INTEGER PRIMARY KEY CHECK(id=1),
                        count INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO legacy_stats(id,count)
                    VALUES(1,0)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS legacy_tag_counts (
                        tag TEXT PRIMARY KEY,
                        count INTEGER NOT NULL
                    )
                    """
                )
                cursor.execute("PRAGMA table_info(files)")
                existing_columns = {row[1] for row in cursor.fetchall()}
                if "meta_json" not in existing_columns:
                    cursor.execute("ALTER TABLE files ADD COLUMN meta_json TEXT")
                if "nsfw_score" not in existing_columns:
                    cursor.execute("ALTER TABLE files ADD COLUMN nsfw_score FLOAT")
                if "face_bbox_json" not in existing_columns:
                    cursor.execute("ALTER TABLE files ADD COLUMN face_bbox_json TEXT")
                if "vector_blob" not in existing_columns:
                    cursor.execute("ALTER TABLE files ADD COLUMN vector_blob BLOB")
                if "last_scanned" not in existing_columns:
                    cursor.execute("ALTER TABLE files ADD COLUMN last_scanned DATETIME")
                connection.commit()
        except sqlite3.Error:
            logger.exception("[DATABASE] [INIT] [ERROR]")

    def get_file_state(self, file_hash: str) -> Optional[int]:
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT flags_done FROM files WHERE hash = ?", (file_hash,))
                row = cursor.fetchone()
                if row is None:
                    return None
                return int(row[0])
        except sqlite3.Error:
            logger.exception("[DATABASE] [GET_FLAGS] [ERROR] %s", file_hash)
            return None

    def get_file_record(self, file_hash: str) -> dict | None:
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT flags_done, meta_json, nsfw_score
                    FROM files
                    WHERE hash = ?
                    """,
                    (file_hash,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                meta_json = json.loads(row[1]) if row[1] else None
                tags = self.get_tags_for_hash(file_hash, connection=connection)
                return {
                    "flags_done": int(row[0]),
                    "meta_json": meta_json,
                    "nsfw_score": row[2],
                    "tags": tags.get("tags", []),
                    "characters": tags.get("characters", []),
                }
        except sqlite3.Error:
            logger.exception("[DATABASE] [GET_FILE] [ERROR] %s", file_hash)
            return None

    def update_file_flags(self, file_hash: str, new_flags: int) -> None:
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    UPDATE files
                    SET flags_done = flags_done | ?
                    WHERE hash = ?
                    """,
                    (new_flags, file_hash),
                )
                connection.commit()
        except sqlite3.Error:
            logger.exception("[DATABASE] [UPDATE_FLAGS] [ERROR] %s", file_hash)

    def save_scan_result(
        self,
        file_hash: str,
        path: str,
        flags_done: int,
        meta: dict | None = None,
        nsfw_score: float | None = None,
        face_bbox: dict | None = None,
        vector_blob: bytes | None = None,
    ) -> None:
        meta_json = json.dumps(meta, ensure_ascii=False) if meta is not None else None
        face_bbox_json = json.dumps(face_bbox, ensure_ascii=False) if face_bbox else None
        scanned_at = datetime.now(timezone.utc).isoformat()
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute("DELETE FROM files WHERE path = ? AND hash != ?", (path, file_hash))
                cursor.execute(
                    """
                    INSERT INTO files (
                        hash,
                        path,
                        flags_done,
                        meta_json,
                        nsfw_score,
                        face_bbox_json,
                        vector_blob,
                        last_scanned
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(hash) DO UPDATE SET
                        path = excluded.path,
                        flags_done = files.flags_done | excluded.flags_done,
                        meta_json = excluded.meta_json,
                        nsfw_score = excluded.nsfw_score,
                        face_bbox_json = excluded.face_bbox_json,
                        vector_blob = excluded.vector_blob,
                        last_scanned = excluded.last_scanned
                    """,
                    (
                        file_hash,
                        path,
                        flags_done,
                        meta_json,
                        nsfw_score,
                        face_bbox_json,
                        sqlite3.Binary(vector_blob) if vector_blob is not None else None,
                        scanned_at,
                    ),
                )
                connection.commit()
        except sqlite3.Error:
            logger.exception("[DATABASE] [SAVE_SCAN] [ERROR] %s", file_hash)

    def upsert_scan_result(
        self,
        file_hash: str,
        path: str,
        flags_done: int,
        meta: dict | None = None,
        nsfw_score: float | None = None,
        face_bbox: dict | None = None,
        vector_blob: bytes | None = None,
    ) -> None:
        meta_json = json.dumps(meta, ensure_ascii=False) if meta is not None else None
        face_bbox_json = json.dumps(face_bbox, ensure_ascii=False) if face_bbox else None
        scanned_at = datetime.now(timezone.utc).isoformat()
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute("DELETE FROM files WHERE path = ? AND hash != ?", (path, file_hash))
                cursor.execute(
                    """
                    INSERT INTO files (
                        hash,
                        path,
                        flags_done,
                        meta_json,
                        nsfw_score,
                        face_bbox_json,
                        vector_blob,
                        last_scanned
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(hash) DO UPDATE SET
                        path = excluded.path,
                        flags_done = files.flags_done | excluded.flags_done,
                        meta_json = COALESCE(excluded.meta_json, files.meta_json),
                        nsfw_score = COALESCE(excluded.nsfw_score, files.nsfw_score),
                        face_bbox_json = COALESCE(excluded.face_bbox_json, files.face_bbox_json),
                        vector_blob = COALESCE(excluded.vector_blob, files.vector_blob),
                        last_scanned = excluded.last_scanned
                    """,
                    (
                        file_hash,
                        path,
                        flags_done,
                        meta_json,
                        nsfw_score,
                        face_bbox_json,
                        sqlite3.Binary(vector_blob) if vector_blob is not None else None,
                        scanned_at,
                    ),
                )
                connection.commit()
        except sqlite3.Error:
            logger.exception("[DATABASE] [UPSERT_SCAN] [ERROR] %s", file_hash)

    def save_tags(
        self,
        file_hash: str,
        tags_list: Iterable[str],
        character_tags_list: Iterable[str],
    ) -> None:
        tags = [tag for tag in dict.fromkeys(tags_list) if tag]
        character_tags = {tag for tag in character_tags_list if tag}

        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute("PRAGMA table_info(tags)")
                columns = {row[1] for row in cursor.fetchall()}
                has_character_column = "is_character" in columns
                if not has_character_column:
                    cursor.execute("ALTER TABLE tags ADD COLUMN is_character INTEGER DEFAULT 0")
                    has_character_column = True

                cursor.execute("DELETE FROM file_tags WHERE file_hash = ?", (file_hash,))

                for tag in tags:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO tags (name, global_count, is_character)
                        VALUES (?, ?, ?)
                        """,
                        (tag, 0, 1 if tag in character_tags else 0),
                    )

                    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag,))
                    tag_row = cursor.fetchone()
                    if tag_row is None:
                        continue

                    cursor.execute(
                        """
                        INSERT INTO file_tags (file_hash, tag_id, confidence)
                        VALUES (?, ?, ?)
                        """,
                        (file_hash, tag_row[0], None),
                    )
                connection.commit()
        except sqlite3.Error:
            logger.exception("[DATABASE] [SAVE_TAGS] [ERROR] %s", file_hash)

    def get_tags_for_hash(self, file_hash: str, connection: sqlite3.Connection | None = None) -> dict:
        try:
            owns_connection = connection is None
            if connection is None:
                connection = sqlite3.connect(self.db_path)
            cursor = connection.cursor()
            cursor.execute("PRAGMA table_info(tags)")
            columns = {row[1] for row in cursor.fetchall()}
            has_character_column = "is_character" in columns
            if has_character_column:
                cursor.execute(
                    """
                    SELECT tags.name, tags.is_character
                    FROM file_tags
                    JOIN tags ON tags.id = file_tags.tag_id
                    WHERE file_tags.file_hash = ?
                    """,
                    (file_hash,),
                )
            else:
                cursor.execute(
                    """
                    SELECT tags.name, 0
                    FROM file_tags
                    JOIN tags ON tags.id = file_tags.tag_id
                    WHERE file_tags.file_hash = ?
                    """,
                    (file_hash,),
                )
            general_tags = []
            character_tags = []
            for name, is_character in cursor.fetchall():
                if has_character_column and is_character:
                    character_tags.append(name)
                else:
                    general_tags.append(name)
            if owns_connection:
                connection.close()
            return {"tags": general_tags, "characters": character_tags}
        except sqlite3.Error:
            logger.exception("[DATABASE] [GET_TAGS] [ERROR] %s", file_hash)
            return {"tags": [], "characters": []}

    def update_tag_trends(self, tags_list: Iterable[str]) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        unique_tags = [tag for tag in dict.fromkeys(tags_list) if tag]
        if not unique_tags:
            return
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute("PRAGMA table_info(tags)")
                columns = {row[1] for row in cursor.fetchall()}
                has_character_column = "is_character" in columns
                if not has_character_column:
                    cursor.execute("ALTER TABLE tags ADD COLUMN is_character INTEGER DEFAULT 0")
                for tag in unique_tags:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO tags (name, global_count, is_character)
                        VALUES (?, ?, ?)
                        """,
                        (tag, 0, 0),
                    )
                    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag,))
                    row = cursor.fetchone()
                    if row is None:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO tag_trends (date, tag_id, day_count)
                        VALUES (?, ?, 1)
                        ON CONFLICT(date, tag_id) DO UPDATE SET
                            day_count = day_count + 1
                        """,
                        (today, row[0]),
                    )
                self._cleanup_tag_trends(cursor)
                connection.commit()
        except sqlite3.Error:
            logger.exception("[DATABASE] [TAG_TRENDS] [ERROR]")

    def _cleanup_tag_trends(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            SELECT tag_id, SUM(day_count)
            FROM tag_trends
            WHERE date < date('now', '-30 day')
            GROUP BY tag_id
            """
        )
        old_rows = cursor.fetchall()
        if not old_rows:
            return
        for tag_id, total in old_rows:
            cursor.execute(
                """
                UPDATE tags
                SET global_count = COALESCE(global_count, 0) + ?
                WHERE id = ?
                """,
                (int(total), int(tag_id)),
            )
        cursor.execute(
            """
            DELETE FROM tag_trends
            WHERE date < date('now', '-30 day')
            """
        )

    def get_weighted_tag_trends(self, limit: int = 50) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT tags.name,
                           SUM(
                               CASE
                                   WHEN tag_trends.date >= date('now', '-1 day') THEN tag_trends.day_count * 3
                                   WHEN tag_trends.date >= date('now', '-7 day') THEN tag_trends.day_count
                                   ELSE 0
                               END
                           ) AS weighted_count
                    FROM tag_trends
                    JOIN tags ON tags.id = tag_trends.tag_id
                    WHERE tag_trends.date >= date('now', '-7 day')
                    GROUP BY tag_trends.tag_id
                    HAVING weighted_count > 0
                    ORDER BY weighted_count DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [
                    {"tag": name, "weighted_count": float(weighted_count)}
                    for name, weighted_count in cursor.fetchall()
                ]
        except sqlite3.Error:
            logger.exception("[DATABASE] [TAG_TRENDS_QUERY] [ERROR]")
            return []

    def record_token_use(self, token: str, mail: str | None = None, webseite: str | None = None) -> None:
        used_at = datetime.now(timezone.utc).isoformat()
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO tokens (token, mail, webseite, last_used)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(token) DO UPDATE SET
                        mail = COALESCE(excluded.mail, tokens.mail),
                        webseite = COALESCE(excluded.webseite, tokens.webseite),
                        last_used = excluded.last_used
                    """,
                    (token, mail, webseite, used_at),
                )
                connection.commit()
        except sqlite3.Error:
            logger.exception("[DATABASE] [TOKEN_USE] [ERROR] %s", token)

    def record_legacy_tags(self, tags_list: Iterable[str]) -> None:
        unique_tags = [tag for tag in tags_list if tag]
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    UPDATE legacy_stats
                    SET count = count + 1
                    WHERE id = 1
                    """
                )
                for tag in unique_tags:
                    cursor.execute(
                        """
                        INSERT INTO legacy_tag_counts(tag, count)
                        VALUES(?, 1)
                        ON CONFLICT(tag) DO UPDATE SET
                            count = count + 1
                        """,
                        (tag,),
                    )
                connection.commit()
        except sqlite3.Error:
            logger.exception("[DATABASE] [LEGACY_TAGS] [ERROR]")

    def get_legacy_stats(self, top_n: int = 5) -> dict:
        try:
            with sqlite3.connect(self.db_path) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT count FROM legacy_stats WHERE id = 1")
                row = cursor.fetchone()
                count = int(row[0]) if row and row[0] is not None else 0
                cursor.execute(
                    """
                    SELECT tag
                    FROM legacy_tag_counts
                    ORDER BY count DESC
                    LIMIT ?
                    """,
                    (top_n,),
                )
                top_tags = [name for (name,) in cursor.fetchall()]
                return {"count": count, "top_tags": top_tags}
        except sqlite3.Error:
            logger.exception("[DATABASE] [LEGACY_STATS] [ERROR]")
            return {"count": 0, "top_tags": []}
