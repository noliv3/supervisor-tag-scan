from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional


class ScannerDB:
    def __init__(self, db_path: str = "scanner.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    hash TEXT PRIMARY KEY,
                    path TEXT UNIQUE,
                    flags_done INTEGER DEFAULT 0,
                    meta_json TEXT,
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
            connection.commit()

    def get_file_state(self, file_hash: str) -> Optional[int]:
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT flags_done FROM files WHERE hash = ?", (file_hash,))
            row = cursor.fetchone()
            if row is None:
                return None
            return int(row[0])

    def update_file_flags(self, file_hash: str, new_flags: int) -> None:
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

    def save_file_scan(self, file_hash: str, path: str, meta: dict, flags_done: int) -> None:
        meta_json = json.dumps(meta, ensure_ascii=False)
        scanned_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM files WHERE path = ? AND hash != ?", (path, file_hash))
            cursor.execute(
                """
                INSERT INTO files (hash, path, flags_done, meta_json, last_scanned)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(hash) DO UPDATE SET
                    path = excluded.path,
                    flags_done = excluded.flags_done,
                    meta_json = excluded.meta_json,
                    last_scanned = excluded.last_scanned
                """,
                (file_hash, path, flags_done, meta_json, scanned_at),
            )
            connection.commit()

    def save_tags(
        self,
        file_hash: str,
        tags_list: Iterable[str],
        character_tags_list: Iterable[str],
    ) -> None:
        tags = [tag for tag in dict.fromkeys(tags_list) if tag]
        character_tags = {tag for tag in character_tags_list if tag}

        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("PRAGMA table_info(tags)")
            columns = {row[1] for row in cursor.fetchall()}
            has_character_column = "is_character" in columns

            cursor.execute("DELETE FROM file_tags WHERE file_hash = ?", (file_hash,))

            for tag in tags:
                if has_character_column:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO tags (name, global_count, is_character)
                        VALUES (?, ?, ?)
                        """,
                        (tag, 0, 1 if tag in character_tags else 0),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO tags (name, global_count)
                        VALUES (?, ?)
                        """,
                        (tag, 0),
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
