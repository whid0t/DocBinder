from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import uuid

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel, Field, field_validator

from .config import settings
from .db import add_notification, audit, connection, init_db, row_dict, utc_now
from .email_validation import validate_email
from .fhir import build_lab_resources, build_rehab_resources, transaction_bundle
from .notifications import queue_doctor_notice, queue_invitation, queue_patient_notice
from .parser import ParseError, PatientMismatch, assert_patient


LEGAL_BASES = {
    "patient_consent_recorded",
    "necessary_for_treatment",
    "other_documented_legal_basis",
}


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def request_id() -> str:
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"CBR-{date}-{secrets.token_hex(2).upper()}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="CareBridge API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestCreate(BaseModel):
    matrix_room_id: str | None = None
    requesting_user_id: str = "@lena.hofer:klinikum.example"
    patient_id: str = "maria-beispiel"
    patient_display: str = "Maria Beispiel"
    patient_birth_date: str = "1961-03-12"
    patient_phone: str = "+43 660 000 0199"
    recipient_name: str = Field(min_length=2, max_length=120)
    recipient_role: str = Field(min_length=2, max_length=160)
    expected_identity_id: str = Field(min_length=3, max_length=120)
    channel: str
    contact: str = Field(min_length=3, max_length=200)
    document_type: str = Field(min_length=2, max_length=120)
    legal_basis: str
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("channel")
    @classmethod
    def valid_channel(cls, value: str) -> str:
        if value not in {"email", "sms"}:
            raise ValueError("channel must be email or sms")
        return value

    @field_validator("legal_basis")
    @classmethod
    def valid_legal_basis(cls, value: str) -> str:
        if value not in LEGAL_BASES:
            raise ValueError("unsupported legal basis")
        return value


class IdentityCheck(BaseModel):
    identity_id: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/demo/identities")
def identities() -> list[dict]:
    return [
        {"id": "AT-EID-EVA-BRANDL", "name": "Dr. Eva Brandl"},
        {"id": "AT-EID-STEFAN-KERN", "name": "Stefan Kern"},
        {"id": "AT-EID-KOLLEGE", "name": "Colleague (misdelivery test)"},
    ]


@app.post("/api/requests", status_code=201)
def create_request(payload: RequestCreate) -> dict:
    warnings: tuple[str, ...] = ()
    contact = payload.contact.strip()
    if payload.channel == "email":
        try:
            email = validate_email(contact)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        contact, warnings = email.normalized, email.warnings

    req_id = request_id()
    raw_token = secrets.token_urlsafe(32)
    invitation_url = f"{settings.public_base_url}/invite/{raw_token}"
    now = utc_now()
    with connection() as db:
        db.execute(
            """INSERT INTO requests (
            id, matrix_room_id, requesting_user_id, patient_id, patient_display,
            patient_birth_date, patient_phone, recipient_name, recipient_role,
            expected_identity_id, channel, contact, document_type, legal_basis,
            reason, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'invitation_sent', ?)""",
            (
                req_id, payload.matrix_room_id, payload.requesting_user_id,
                payload.patient_id, payload.patient_display, payload.patient_birth_date,
                payload.patient_phone, payload.recipient_name, payload.recipient_role,
                payload.expected_identity_id, payload.channel, contact,
                payload.document_type, payload.legal_basis, payload.reason, now,
            ),
        )
        db.execute(
            "INSERT INTO invitations (request_id, token_hash) VALUES (?, ?)",
            (req_id, token_hash(raw_token)),
        )
        audit(db, req_id, "request_confirmed", payload.requesting_user_id, details={
            "legal_basis": payload.legal_basis,
            "reason": payload.reason,
        })
        queue_invitation(
            db,
            request_id=req_id,
            channel=payload.channel,
            destination=contact,
            action_url=invitation_url,
        )
        audit(db, req_id, "request_sent", payload.requesting_user_id, details={
            "channel": payload.channel,
            "recipient": payload.recipient_name,
        })
        if payload.patient_phone:
            queue_patient_notice(db, req_id, payload.patient_phone, "Dr. Lena Hofer")
            audit(db, req_id, "patient_notified", payload.requesting_user_id)

    return {
        "id": req_id,
        "status": "invitation_sent",
        "invitation_url": invitation_url,
        "warnings": warnings,
    }


@app.get("/api/requests")
def list_requests(limit: int = 20) -> list[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM requests ORDER BY created_at DESC LIMIT ?",
            (min(max(limit, 1), 100),),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/requests/{req_id}")
def get_request(req_id: str) -> dict:
    with connection() as db:
        row = db.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Request not found")
    return dict(row)


@app.get("/api/requests/{req_id}/audit")
def request_audit(req_id: str) -> list[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM audit_events WHERE request_id=? ORDER BY id", (req_id,)
        ).fetchall()
    return [{**dict(row), "details": json.loads(row["details_json"])} for row in rows]


@app.post("/api/requests/{req_id}/revoke")
def revoke_request(req_id: str, actor: str = "@lena.hofer:klinikum.example") -> dict:
    with connection() as db:
        request = db.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
        if not request:
            raise HTTPException(404, "Request not found")
        if request["status"] == "revoked":
            return {"id": req_id, "status": "revoked"}
        if request["status"] == "filed":
            raise HTTPException(409, "A filed request cannot be revoked")
        now = utc_now()
        db.execute("UPDATE requests SET status='revoked', revoked_at=? WHERE id=?", (now, req_id))
        db.execute("UPDATE invitations SET revoked_at=? WHERE request_id=?", (now, req_id))
        audit(db, req_id, "request_revoked", actor)
    return {"id": req_id, "status": "revoked"}


def _invitation(db: sqlite3.Connection, raw_token: str) -> tuple[sqlite3.Row, sqlite3.Row]:
    invitation = db.execute(
        "SELECT * FROM invitations WHERE token_hash=?", (token_hash(raw_token),)
    ).fetchone()
    if not invitation:
        raise HTTPException(404, "This invitation is unavailable.")
    request = db.execute("SELECT * FROM requests WHERE id=?", (invitation["request_id"],)).fetchone()
    if invitation["locked_at"] or invitation["used_at"] or invitation["revoked_at"]:
        raise HTTPException(410, "This invitation is unavailable.")
    return invitation, request


@app.get("/api/invitations/{raw_token}")
def open_invitation(raw_token: str) -> dict:
    with connection() as db:
        invitation, request = _invitation(db, raw_token)
        audit(db, request["id"], "link_opened", "unverified_recipient")
    return {"request_reference": request["id"], "status": "identity_required"}


@app.post("/api/invitations/{raw_token}/verify")
def verify_identity(raw_token: str, payload: IdentityCheck) -> dict:
    with connection() as db:
        invitation, request = _invitation(db, raw_token)
        if not secrets.compare_digest(payload.identity_id, request["expected_identity_id"]):
            attempts = invitation["failed_attempts"] + 1
            locked = attempts >= 5
            now = utc_now() if locked else None
            db.execute(
                "UPDATE invitations SET failed_attempts=?, locked_at=? WHERE request_id=?",
                (attempts, now, request["id"]),
            )
            audit(db, request["id"], "identity_checked", payload.identity_id, "failure", {
                "attempt": attempts,
            })
            audit(db, request["id"], "misdelivery_caught", payload.identity_id, "blocked")
            if locked:
                db.execute("UPDATE requests SET status='identity_locked' WHERE id=?", (request["id"],))
                queue_doctor_notice(
                    db, request,
                    f"CareBridge request {request['id']} was locked after repeated failed identity checks.",
                )
            db.commit()
            raise HTTPException(403, "Identity verification failed.")

        verification_token = secrets.token_urlsafe(32)
        db.execute(
            "INSERT OR REPLACE INTO verification_sessions VALUES (?, ?, ?, ?)",
            (token_hash(verification_token), request["id"], payload.identity_id, utc_now()),
        )
        db.execute("UPDATE requests SET status='identity_verified' WHERE id=?", (request["id"],))
        audit(db, request["id"], "identity_checked", payload.identity_id)
    return {"verification_token": verification_token}


def _verified_request(
    db: sqlite3.Connection, raw_token: str, verification_token: str | None
) -> tuple[sqlite3.Row, sqlite3.Row]:
    invitation, request = _invitation(db, raw_token)
    if not verification_token:
        raise HTTPException(401, "Identity verification is required.")
    session = db.execute(
        "SELECT * FROM verification_sessions WHERE token_hash=? AND request_id=?",
        (token_hash(verification_token), request["id"]),
    ).fetchone()
    if not session:
        raise HTTPException(401, "Identity verification is required.")
    return request, session


@app.get("/api/invitations/{raw_token}/details")
def invitation_details(raw_token: str, x_verification_token: str | None = Header(None)) -> dict:
    with connection() as db:
        request, _ = _verified_request(db, raw_token, x_verification_token)
    return {
        "request_reference": request["id"],
        "patient_display": request["patient_display"],
        "patient_birth_date": request["patient_birth_date"],
        "document_type": request["document_type"],
        "requesting_clinician": "Dr. Lena Hofer",
    }


@app.post("/api/invitations/{raw_token}/submit")
async def submit_document(
    raw_token: str,
    x_verification_token: str | None = Header(None),
    patient_name: str = Form(...),
    patient_birth_date: str = Form(...),
    markdown: str = Form(""),
    file: UploadFile | None = File(None),
) -> dict:
    text = markdown.strip()
    if file:
        if not file.filename or not file.filename.lower().endswith(".md"):
            raise HTTPException(422, "Only Markdown (.md) files are supported.")
        text = (await file.read()).decode("utf-8").strip()
    if not text:
        raise HTTPException(422, "Upload a Markdown file or paste Markdown text.")

    with connection() as db:
        request, session = _verified_request(db, raw_token, x_verification_token)
        if (
            patient_name.strip().casefold() != request["patient_display"].casefold()
            or patient_birth_date != request["patient_birth_date"]
        ):
            audit(db, request["id"], "patient_mismatch", session["identity_id"], "blocked")
            audit(db, request["id"], "misdelivery_caught", session["identity_id"], "blocked")
            db.execute("UPDATE requests SET status='patient_mismatch' WHERE id=?", (request["id"],))
            queue_doctor_notice(db, request, f"Patient mismatch blocked for request {request['id']}.")
            db.commit()
            raise HTTPException(409, "The supplied patient details do not match the request.")
        try:
            assert_patient(text, request["patient_display"], request["patient_birth_date"])
            if "lab" in request["document_type"].casefold():
                resources = build_lab_resources(
                    text, request["patient_id"], request["recipient_name"], session["identity_id"]
                )
            else:
                resources = build_rehab_resources(
                    text, request["patient_id"], request["recipient_name"], session["identity_id"]
                )
        except PatientMismatch as exc:
            audit(db, request["id"], "patient_mismatch", session["identity_id"], "blocked")
            audit(db, request["id"], "misdelivery_caught", session["identity_id"], "blocked")
            db.execute("UPDATE requests SET status='patient_mismatch' WHERE id=?", (request["id"],))
            queue_doctor_notice(db, request, f"Wrong-patient document blocked for request {request['id']}.")
            db.commit()
            raise HTTPException(409, str(exc)) from exc
        except ParseError as exc:
            audit(db, request["id"], "parse_failed", session["identity_id"], "failure")
            db.execute("UPDATE requests SET status='parse_failed' WHERE id=?", (request["id"],))
            queue_doctor_notice(db, request, f"Document parsing failed for request {request['id']}.")
            db.commit()
            raise HTTPException(422, str(exc)) from exc

        submission_id = str(uuid.uuid4())
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        db.execute(
            """INSERT INTO submissions
            (id, request_id, submitter_identity, original_text, content_hash, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'processing', ?)""",
            (submission_id, request["id"], session["identity_id"], text, content_hash, utc_now()),
        )
        audit(db, request["id"], "answer_sent", session["identity_id"])
        db.execute("UPDATE requests SET status='processing' WHERE id=?", (request["id"],))

        for resource in resources:
            db.execute(
                """INSERT INTO fhir_resources
                (id, request_id, resource_type, resource_json, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (resource["id"], request["id"], resource["resourceType"], json.dumps(resource), utc_now()),
            )

        try:
            patient_path = Path("/scenario/patient.json")
            if patient_path.exists():
                patient_response = httpx.put(
                    f"{settings.fhir_base_url}/Patient/{request['patient_id']}",
                    content=patient_path.read_bytes(),
                    headers={"Content-Type": "application/fhir+json"},
                    timeout=20,
                )
                patient_response.raise_for_status()
            response = httpx.post(
                settings.fhir_base_url,
                json=transaction_bundle(resources),
                headers={"Content-Type": "application/fhir+json"},
                timeout=20,
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            db.execute("UPDATE requests SET status='filing_failed' WHERE id=?", (request["id"],))
            db.execute(
                "UPDATE submissions SET status='filing_failed', error=? WHERE id=?",
                (str(exc)[:500], submission_id),
            )
            audit(db, request["id"], "filing_failed", "carebridge-backend", "failure")
            queue_doctor_notice(db, request, f"FHIR filing failed for request {request['id']}; retry is required.")
            db.commit()
            raise HTTPException(503, "The document was checked but could not be filed. The doctor was notified.") from exc

        now = utc_now()
        db.execute("UPDATE fhir_resources SET stored_remotely=1 WHERE request_id=?", (request["id"],))
        db.execute("UPDATE submissions SET status='filed' WHERE id=?", (submission_id,))
        db.execute("UPDATE requests SET status='filed' WHERE id=?", (request["id"],))
        db.execute("UPDATE invitations SET used_at=? WHERE request_id=?", (now, request["id"]))
        audit(db, request["id"], "answer_filed", "carebridge-backend")
        queue_doctor_notice(db, request, f"Request {request['id']} was verified and filed successfully in FHIR.")
    return {"request_id": request["id"], "status": "filed", "resources": len(resources)}


@app.get("/api/demo/sms")
def sms_outbox() -> list[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM notifications WHERE channel='sms' ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/demo/notifications")
def all_notifications() -> list[dict]:
    with connection() as db:
        rows = db.execute("SELECT * FROM notifications ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


@app.get("/api/internal/matrix-notifications")
def matrix_notifications() -> list[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM notifications WHERE channel='matrix' AND status='queued' ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/internal/matrix-notifications/{notification_id}/delivered")
def mark_matrix_delivered(notification_id: int) -> dict:
    with connection() as db:
        db.execute(
            "UPDATE notifications SET status='delivered', delivered_at=? WHERE id=? AND channel='matrix'",
            (utc_now(), notification_id),
        )
    return {"id": notification_id, "status": "delivered"}


@app.get("/api/requests/{req_id}/fhir")
def request_fhir(req_id: str) -> list[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT resource_json FROM fhir_resources WHERE request_id=? ORDER BY rowid", (req_id,)
        ).fetchall()
    return [json.loads(row["resource_json"]) for row in rows]

