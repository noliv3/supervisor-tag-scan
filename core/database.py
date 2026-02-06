from __future__ import annotations

import sqlite3
from typing import Optional


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
