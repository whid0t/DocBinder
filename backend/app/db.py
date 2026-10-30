from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Iterator

from .config import settings


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY,
  matrix_room_id TEXT,
  requesting_user_id TEXT NOT NULL,
  patient_id TEXT NOT NULL,
  patient_display TEXT NOT NULL,
  patient_birth_date TEXT NOT NULL,
  patient_phone TEXT,
  recipient_name TEXT NOT NULL,
  recipient_role TEXT NOT NULL,
  expected_identity_id TEXT,
  channel TEXT NOT NULL CHECK(channel IN ('email','sms')),
  contact TEXT NOT NULL,
  document_type TEXT NOT NULL,
  document_type_code TEXT,
  legal_basis TEXT NOT NULL,
  purpose_or_legal_basis TEXT,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS invitations (
  request_id TEXT PRIMARY KEY REFERENCES requests(id),
  token_hash TEXT NOT NULL UNIQUE,
  failed_attempts INTEGER NOT NULL DEFAULT 0,
  locked_at TEXT,
  used_at TEXT,
  revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS verification_sessions (
  token_hash TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES requests(id),
  identity_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submissions (
  id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES requests(id),
  batch_id TEXT,
  filename TEXT,
  submitter_identity TEXT NOT NULL,
  original_text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fhir_resources (
  id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES requests(id),
  submission_id TEXT,
  resource_type TEXT NOT NULL,
  resource_json TEXT NOT NULL,
  stored_remotely INTEGER NOT NULL DEFAULT 0,
  remote_url TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT,
  event_type TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT,
  audience TEXT NOT NULL,
  channel TEXT NOT NULL,
  destination TEXT NOT NULL,
  subject TEXT,
  body TEXT NOT NULL,
  action_url TEXT,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS audit_request_idx ON audit_events(request_id, created_at);
CREATE INDEX IF NOT EXISTS notification_channel_idx ON notifications(channel, created_at);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path = path.with_name("carebridge.db")
    if not path.exists() and legacy_path.exists():
        shutil.copy2(legacy_path, path)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    with connection() as db:
        db.executescript(SCHEMA)
        _add_missing_columns(db, "requests", {
            "document_type_code": "TEXT",
            "purpose_or_legal_basis": "TEXT",
        })
        _add_missing_columns(db, "submissions", {
            "batch_id": "TEXT",
            "filename": "TEXT",
        })
        _add_missing_columns(db, "fhir_resources", {
            "submission_id": "TEXT",
            "remote_url": "TEXT",
        })
        db.execute(
            "UPDATE notifications SET body=replace(body, 'CareBridge', 'DocBinder'), "
            "subject=replace(subject, 'CareBridge', 'DocBinder')"
        )
        db.execute(
            """UPDATE notifications
            SET body=? || request_id || ?
            WHERE audience='patient' AND channel='sms'""",
            (
                f"{settings.clinic_name} ({settings.doctor_name}) initiated healthcare document request ",
                ". REPLY WITH 1 TO ACCEPT, 0 TO DECLINE. If an answer is NOT RECEIVED in 6 hours, "
                "you will receive a call to confirm.",
            ),
        )
        db.execute(
            "UPDATE fhir_resources SET remote_url=replace(remote_url, ?, ?) "
            "WHERE remote_url LIKE ?",
            (settings.fhir_base_url, settings.fhir_public_url, f"{settings.fhir_base_url}%"),
        )


def _add_missing_columns(
    db: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def audit(
    db: sqlite3.Connection,
    request_id: str | None,
    event_type: str,
    actor_id: str,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
) -> None:
    db.execute(
        """INSERT INTO audit_events
        (request_id, event_type, actor_id, outcome, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (request_id, event_type, actor_id, outcome, json.dumps(details or {}), utc_now()),
    )


def add_notification(
    db: sqlite3.Connection,
    *,
    request_id: str,
    audience: str,
    channel: str,
    destination: str,
    body: str,
    subject: str | None = None,
    action_url: str | None = None,
    status: str = "queued",
) -> int:
    cursor = db.execute(
        """INSERT INTO notifications
        (request_id, audience, channel, destination, subject, body, action_url, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (request_id, audience, channel, destination, subject, body, action_url, status, utc_now()),
    )
    return int(cursor.lastrowid)

