from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3


class ConversationStore:
    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("BOT_DATABASE_PATH", "/data/bot.db"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS conversations (
              room_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              step TEXT NOT NULL,
              data_json TEXT NOT NULL,
              PRIMARY KEY(room_id, user_id)
            )""")

    def connect(self):
        return sqlite3.connect(self.path)

    def get(self, room_id: str, user_id: str) -> tuple[str, dict] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT step, data_json FROM conversations WHERE room_id=? AND user_id=?",
                (room_id, user_id),
            ).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def save(self, room_id: str, user_id: str, step: str, data: dict) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO conversations VALUES (?, ?, ?, ?)",
                (room_id, user_id, step, json.dumps(data)),
            )

    def clear(self, room_id: str, user_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM conversations WHERE room_id=? AND user_id=?", (room_id, user_id))

