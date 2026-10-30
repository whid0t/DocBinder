from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
import hashlib
import json
import re
import secrets
import sqlite3
import uuid

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from .config import settings
from .db import audit, connection, init_db, utc_now
from .email_validation import validate_email
from .fhir import build_lab_resources, build_rehab_resources, transaction_bundle
from .identity import names_match, normalize_person_name
from .notifications import queue_doctor_notice, queue_invitation, queue_patient_notice
from .parser import ParseError, PatientMismatch, assert_patient, is_laboratory_document, is_rehabilitation_document
from .summary import build_observation_summary


DOCUMENT_TYPES = {
    "laboratory_results": "Laboratory results",
    "rehabilitation_report": "Rehabilitation discharge report",
}
PURPOSES = {"necessary for treatment", "transfer of patient", "optimize treatment"}
PATIENT_ID_RE = re.compile(r"^[A-Za-z0-9.-]{1,64}$")
MAX_BATCH_BYTES = 3 * 1024 * 1024


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def request_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"DBR-{today}-{secrets.token_hex(2).upper()}"


def _legacy_document_type(value: str | None) -> str | None:
    normalized = (value or "").casefold()
    if "lab" in normalized or "blood" in normalized:
        return "laboratory_results"
    if "rehab" in normalized or "discharge" in normalized:
        return "rehabilitation_report"
    return None


def _request_document_type(request: sqlite3.Row) -> str:
    code = request["document_type_code"] or _legacy_document_type(request["document_type"])
    if code not in DOCUMENT_TYPES:
        raise HTTPException(409, "This legacy request has an unsupported document type.")
    return code


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="DocBinder API",
    description="Synthetic clinical document exchange for the interoperability hackathon.",
    version="0.2.0",
    lifespan=lifespan,
)
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
    patient_name: str | None = None
    patient_display: str | None = None
    patient_birth_date: str = "1961-03-12"
    patient_phone: str = "+43 660 000 0199"
    recipient_name: str = Field(min_length=2, max_length=120)
    recipient_role: str = Field(min_length=2, max_length=160)
    channel: str
    contact: str = Field(min_length=3, max_length=200)
    document_type_code: str | None = None
    document_type: str | None = None
    purpose_or_legal_basis: str | None = None
    legal_basis: str | None = None
    reason: str = Field(min_length=3, max_length=500)
    clinic_name: str = settings.clinic_name
    doctor_name: str = settings.doctor_name

    @field_validator("channel")
    @classmethod
    def valid_channel(cls, value: str) -> str:
        value = value.casefold().strip()
        if value not in {"email", "sms"}:
            raise ValueError("channel must be email or sms")
        return value

    @model_validator(mode="after")
    def validate_request(self):
        self.patient_name = (self.patient_name or self.patient_display or "").strip()
        self.document_type_code = self.document_type_code or _legacy_document_type(self.document_type)
        self.purpose_or_legal_basis = (
            self.purpose_or_legal_basis or self.legal_basis or ""
        ).strip().casefold()
        if not self.patient_name:
            raise ValueError("patient_name is required")
        if not PATIENT_ID_RE.fullmatch(self.patient_id):
            raise ValueError("patient_id may contain letters, digits, periods, and hyphens")
        try:
            date.fromisoformat(self.patient_birth_date)
        except ValueError as exc:
            raise ValueError("patient_birth_date must be a valid YYYY-MM-DD date") from exc
        if self.document_type_code not in DOCUMENT_TYPES:
            raise ValueError("document_type_code must be laboratory_results or rehabilitation_report")
        if self.purpose_or_legal_basis not in PURPOSES:
            raise ValueError(
                "purpose_or_legal_basis must be necessary for treatment, transfer of patient, or optimize treatment"
            )
        return self


class IdentityCheck(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "DocBinder"}


def _patient_resource(payload: RequestCreate) -> dict:
    parts = payload.patient_name.split()
    patient = {
        "resourceType": "Patient",
        "id": payload.patient_id,
        "active": True,
        "name": [{"use": "official", "family": parts[-1], "given": parts[:-1]}],
        "birthDate": payload.patient_birth_date,
    }
    if payload.patient_phone:
        patient["telecom"] = [{"system": "phone", "value": payload.patient_phone, "use": "mobile"}]
    return patient


def _fhir_patient_name(patient: dict) -> str:
    name = next(iter(patient.get("name", [])), {})
    return " ".join([*name.get("given", []), name.get("family", "")]).strip()


def _ensure_patient(payload: RequestCreate) -> bool:
    url = f"{settings.fhir_base_url}/Patient/{payload.patient_id}"
    try:
        response = httpx.get(url, headers={"Accept": "application/fhir+json"}, timeout=10)
        if response.status_code == 404:
            created = httpx.put(
                url,
                json=_patient_resource(payload),
                headers={"Content-Type": "application/fhir+json"},
                timeout=15,
            )
            created.raise_for_status()
            return True
        response.raise_for_status()
        patient = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(503, "The FHIR patient service is unavailable.") from exc
    if (
        normalize_person_name(_fhir_patient_name(patient)) != normalize_person_name(payload.patient_name)
        or patient.get("birthDate") != payload.patient_birth_date
    ):
        raise HTTPException(409, "The patient ID already exists with different demographics.")
    return False


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
    try:
        patient_created = _ensure_patient(payload)
    except HTTPException as exc:
        if exc.status_code == 409:
            with connection() as db:
                audit(db, None, "patient_conflict", payload.requesting_user_id, "blocked", {
                    "candidate_request_id": req_id, "patient_id": payload.patient_id,
                })
        raise
    raw_token = secrets.token_urlsafe(32)
    invitation_url = f"{settings.public_base_url}/invite/{raw_token}"
    now = utc_now()
    display_type = DOCUMENT_TYPES[payload.document_type_code]
    with connection() as db:
        db.execute(
            """INSERT INTO requests (
            id, matrix_room_id, requesting_user_id, patient_id, patient_display,
            patient_birth_date, patient_phone, recipient_name, recipient_role,
            expected_identity_id, channel, contact, document_type, document_type_code,
            legal_basis, purpose_or_legal_basis, reason, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, 'invitation_sent', ?)""",
            (
                req_id, payload.matrix_room_id, payload.requesting_user_id,
                payload.patient_id, payload.patient_name, payload.patient_birth_date,
                payload.patient_phone, payload.recipient_name.strip(), payload.recipient_role.strip(),
                payload.channel, contact, display_type, payload.document_type_code,
                payload.purpose_or_legal_basis, payload.purpose_or_legal_basis,
                payload.reason.strip(), now,
            ),
        )
        db.execute("INSERT INTO invitations (request_id, token_hash) VALUES (?, ?)", (req_id, token_hash(raw_token)))
        audit(db, req_id, "request_confirmed", payload.requesting_user_id, details={
            "purpose_or_legal_basis": payload.purpose_or_legal_basis,
            "reason": payload.reason,
        })
        audit(db, req_id, "patient_created" if patient_created else "patient_matched", payload.requesting_user_id)
        queue_invitation(
            db, request_id=req_id, channel=payload.channel,
            destination=contact, action_url=invitation_url,
        )
        audit(db, req_id, "request_sent", payload.requesting_user_id, details={
            "channel": payload.channel, "recipient": payload.recipient_name,
        })
        if payload.patient_phone:
            queue_patient_notice(db, req_id, payload.patient_phone, payload.clinic_name, payload.doctor_name)
            audit(db, req_id, "patient_notified", payload.requesting_user_id)
    return {"id": req_id, "status": "invitation_sent", "invitation_url": invitation_url, "warnings": warnings}


@app.get("/api/requests")
def list_requests(limit: int = 20) -> list[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM requests ORDER BY created_at DESC LIMIT ?",
            (min(max(limit, 1), 100),),
        ).fetchall()
    return [dict(row) for row in rows]


def _get_request(db: sqlite3.Connection, req_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Request not found")
    return row


@app.get("/api/requests/{req_id}")
def get_request(req_id: str) -> dict:
    with connection() as db:
        return dict(_get_request(db, req_id))


@app.get("/api/requests/{req_id}/audit")
def request_audit(req_id: str) -> list[dict]:
    with connection() as db:
        _get_request(db, req_id)
        rows = db.execute("SELECT * FROM audit_events WHERE request_id=? ORDER BY id", (req_id,)).fetchall()
    return [{**dict(row), "details": json.loads(row["details_json"])} for row in rows]


@app.post("/api/requests/{req_id}/revoke")
def revoke_request(req_id: str, actor: str = "@lena.hofer:klinikum.example") -> dict:
    with connection() as db:
        request = _get_request(db, req_id)
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
    invitation = db.execute("SELECT * FROM invitations WHERE token_hash=?", (token_hash(raw_token),)).fetchone()
    if not invitation:
        raise HTTPException(404, "This invitation is unavailable.")
    request = _get_request(db, invitation["request_id"])
    if invitation["locked_at"] or invitation["used_at"] or invitation["revoked_at"]:
        raise HTTPException(410, "This invitation is unavailable.")
    return invitation, request


@app.get("/api/invitations/{raw_token}")
def open_invitation(raw_token: str) -> dict:
    with connection() as db:
        _, request = _invitation(db, raw_token)
        audit(db, request["id"], "link_opened", "unverified_recipient")
    return {"request_reference": request["id"], "status": "identity_required"}


@app.post("/api/invitations/{raw_token}/verify")
def verify_identity(raw_token: str, payload: IdentityCheck) -> dict:
    entered = normalize_person_name(payload.full_name)
    if not entered:
        raise HTTPException(422, "Enter your full name.")
    with connection() as db:
        invitation, request = _invitation(db, raw_token)
        if not names_match(payload.full_name, request["recipient_name"]):
            attempts = invitation["failed_attempts"] + 1
            locked = attempts >= 5
            db.execute(
                "UPDATE invitations SET failed_attempts=?, locked_at=? WHERE request_id=?",
                (attempts, utc_now() if locked else None, request["id"]),
            )
            audit(db, request["id"], "identity_checked", entered, "failure", {"attempt": attempts})
            audit(db, request["id"], "misdelivery_caught", entered, "blocked")
            if locked:
                db.execute("UPDATE requests SET status='identity_locked' WHERE id=?", (request["id"],))
                queue_doctor_notice(db, request, f"DocBinder request {request['id']} was locked after repeated failed identity checks.")
            db.commit()
            raise HTTPException(403, "Identity verification failed.")
        verification_token = secrets.token_urlsafe(32)
        db.execute(
            "INSERT OR REPLACE INTO verification_sessions VALUES (?, ?, ?, ?)",
            (token_hash(verification_token), request["id"], entered, utc_now()),
        )
        db.execute("UPDATE requests SET status='identity_verified' WHERE id=?", (request["id"],))
        audit(db, request["id"], "identity_checked", entered)
    return {"verification_token": verification_token}


def _verified_request(
    db: sqlite3.Connection, raw_token: str, verification_token: str | None
) -> tuple[sqlite3.Row, sqlite3.Row]:
    _, request = _invitation(db, raw_token)
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
        code = _request_document_type(request)
    return {
        "request_reference": request["id"],
        "patient_display": request["patient_display"],
        "patient_birth_date": request["patient_birth_date"],
        "document_type": DOCUMENT_TYPES[code],
        "document_type_code": code,
        "requesting_clinician": settings.doctor_name,
    }


async def _read_documents(files: list[UploadFile] | None, markdown: str) -> list[tuple[str, str, str]]:
    documents: list[tuple[str, str, str]] = []
    total = len(markdown.encode())
    if markdown.strip():
        content = markdown.strip()
        documents.append(("pasted-document.md", content, hashlib.sha256(content.encode()).hexdigest()))
    for upload in files or []:
        if not upload.filename or not upload.filename.lower().endswith(".md"):
            raise HTTPException(422, "Only Markdown (.md) files are supported.")
        raw = await upload.read()
        total += len(raw)
        try:
            content = raw.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise HTTPException(422, f"{upload.filename} must be UTF-8 Markdown.") from exc
        if not content:
            raise HTTPException(422, f"{upload.filename} is empty.")
        documents.append((upload.filename, content, hashlib.sha256(content.encode()).hexdigest()))
    if not 1 <= len(documents) <= 3:
        raise HTTPException(422, "Submit between one and three Markdown documents.")
    if total > MAX_BATCH_BYTES:
        raise HTTPException(413, "The document batch exceeds the 3 MiB demo limit.")
    hashes = [item[2] for item in documents]
    if len(hashes) != len(set(hashes)):
        raise HTTPException(422, "The batch contains duplicate documents.")
    return documents


def _assert_consistent_observation_units(resources: list[dict]) -> None:
    units: dict[str, str] = {}
    for resource in resources:
        if resource.get("resourceType") != "Observation":
            continue
        coding = next((item for item in resource.get("code", {}).get("coding", []) if item.get("system") == "http://loinc.org"), {})
        code = coding.get("code")
        quantity = resource.get("valueQuantity", {})
        unit = quantity.get("code") or quantity.get("unit") or ""
        if code in units and units[code] != unit:
            raise ParseError(f"LOINC {code} uses inconsistent units within this batch.")
        if code:
            units[code] = unit


@app.post("/api/invitations/{raw_token}/submit")
async def submit_document_batch(
    raw_token: str,
    x_verification_token: str | None = Header(None),
    patient_name: str = Form(...),
    patient_birth_date: str = Form(...),
    markdown: str = Form(""),
    files: list[UploadFile] | None = File(None),
) -> dict:
    documents = await _read_documents(files, markdown)
    with connection() as db:
        request, session = _verified_request(db, raw_token, x_verification_token)
        document_type = _request_document_type(request)
        if (
            normalize_person_name(patient_name) != normalize_person_name(request["patient_display"])
            or patient_birth_date != request["patient_birth_date"]
        ):
            _record_patient_mismatch(db, request, session["identity_id"], "Supplied patient details mismatch")
            db.commit()
            raise HTTPException(409, "The supplied patient details do not match the request.")

        batch_id = str(uuid.uuid4())
        prepared: list[dict] = []
        try:
            for filename, text, content_hash in documents:
                assert_patient(text, request["patient_display"], request["patient_birth_date"])
                if document_type == "laboratory_results":
                    if not is_laboratory_document(text):
                        raise ParseError(f"{filename} is not a laboratory-results document.")
                    resources = build_lab_resources(text, request["patient_id"], request["recipient_name"], session["identity_id"])
                else:
                    if not is_rehabilitation_document(text):
                        raise ParseError(f"{filename} is not a rehabilitation discharge report.")
                    resources = build_rehab_resources(text, request["patient_id"], request["recipient_name"], session["identity_id"])
                prepared.append({
                    "submission_id": str(uuid.uuid4()), "filename": filename,
                    "text": text, "hash": content_hash, "resources": resources,
                })
            _assert_consistent_observation_units([
                resource for item in prepared for resource in item["resources"]
            ])
        except PatientMismatch as exc:
            _record_patient_mismatch(db, request, session["identity_id"], str(exc))
            db.commit()
            raise HTTPException(409, str(exc)) from exc
        except ParseError as exc:
            audit(db, request["id"], "parse_failed", session["identity_id"], "failure", {"error": str(exc)})
            db.execute("UPDATE requests SET status='parse_failed' WHERE id=?", (request["id"],))
            queue_doctor_notice(db, request, f"Document parsing failed for request {request['id']}.")
            db.commit()
            raise HTTPException(422, str(exc)) from exc

        all_resources: list[dict] = []
        resource_ids: list[str] = []
        for item in prepared:
            db.execute(
                """INSERT INTO submissions
                (id, request_id, batch_id, filename, submitter_identity, original_text,
                 content_hash, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'processing', ?)""",
                (
                    item["submission_id"], request["id"], batch_id, item["filename"],
                    session["identity_id"], item["text"], item["hash"], utc_now(),
                ),
            )
            for resource in item["resources"]:
                resource_ids.append(resource["id"])
                all_resources.append(resource)
                db.execute(
                    """INSERT INTO fhir_resources
                    (id, request_id, submission_id, resource_type, resource_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        resource["id"], request["id"], item["submission_id"],
                        resource["resourceType"], json.dumps(resource), utc_now(),
                    ),
                )
        audit(db, request["id"], "answer_sent", session["identity_id"], details={
            "batch_id": batch_id, "documents": len(prepared),
        })
        db.execute("UPDATE requests SET status='processing' WHERE id=?", (request["id"],))
        try:
            response = httpx.post(
                settings.fhir_base_url,
                json=transaction_bundle(all_resources),
                headers={"Content-Type": "application/fhir+json"},
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            db.execute("UPDATE requests SET status='filing_failed' WHERE id=?", (request["id"],))
            db.execute(
                "UPDATE submissions SET status='filing_failed', error=? WHERE batch_id=?",
                (str(exc)[:500], batch_id),
            )
            audit(db, request["id"], "filing_failed", "docbinder-backend", "failure")
            queue_doctor_notice(db, request, f"FHIR filing failed for request {request['id']}; retry is required.")
            db.commit()
            raise HTTPException(503, "The batch was checked but could not be filed. The doctor was notified.") from exc

        placeholders = ",".join("?" for _ in resource_ids)
        db.execute(
            f"UPDATE fhir_resources SET stored_remotely=1, remote_url=? || '/' || resource_type || '/' || id WHERE id IN ({placeholders})",
            (settings.fhir_public_url, *resource_ids),
        )
        db.execute("UPDATE submissions SET status='filed' WHERE batch_id=?", (batch_id,))
        db.execute("UPDATE requests SET status='filed' WHERE id=?", (request["id"],))
        db.execute("UPDATE invitations SET used_at=? WHERE request_id=?", (utc_now(), request["id"]))
        audit(db, request["id"], "answer_filed", "docbinder-backend", details={
            "documents": len(prepared), "resources": len(all_resources),
        })
        summary = build_observation_summary(all_resources)
        detail_url = f"{settings.internal_public_url}/requests/{request['id']}"
        queue_doctor_notice(
            db,
            request,
            f"Request {request['id']} filed: {len(prepared)} document(s), {len(all_resources)} FHIR resource(s).\n"
            f"{summary['text']}\nView request: {detail_url}",
        )
    return {
        "request_id": request["id"], "status": "filed", "documents": len(prepared),
        "resources": len(all_resources), "summary": summary,
    }


def _record_patient_mismatch(db: sqlite3.Connection, request: sqlite3.Row, actor: str, error: str) -> None:
    audit(db, request["id"], "patient_mismatch", actor, "blocked", {"error": error})
    audit(db, request["id"], "misdelivery_caught", actor, "blocked")
    db.execute("UPDATE requests SET status='patient_mismatch' WHERE id=?", (request["id"],))
    queue_doctor_notice(db, request, f"Wrong-patient document blocked for request {request['id']}.")


def _resource_rows(db: sqlite3.Connection, req_id: str) -> list[dict]:
    rows = db.execute(
        "SELECT * FROM fhir_resources WHERE request_id=? ORDER BY created_at, rowid", (req_id,)
    ).fetchall()
    return [{**dict(row), "resource": json.loads(row["resource_json"])} for row in rows]


@app.get("/api/requests/{req_id}/detail")
def request_detail(req_id: str) -> dict:
    with connection() as db:
        request = dict(_get_request(db, req_id))
        submissions = [dict(row) for row in db.execute(
            """SELECT id, request_id, batch_id, filename, submitter_identity, original_text,
               content_hash, status, error, created_at FROM submissions
               WHERE request_id=? ORDER BY created_at, rowid""",
            (req_id,),
        ).fetchall()]
        resources = _resource_rows(db, req_id)
        audits = [
            {**dict(row), "details": json.loads(row["details_json"])}
            for row in db.execute("SELECT * FROM audit_events WHERE request_id=? ORDER BY id", (req_id,)).fetchall()
        ]
    return {
        "request": request,
        "submissions": submissions,
        "fhir_resources": resources,
        "summary": build_observation_summary(item["resource"] for item in resources),
        "audit": audits,
    }


@app.get("/api/requests/{req_id}/summary")
def request_summary(req_id: str) -> dict:
    with connection() as db:
        _get_request(db, req_id)
        resources = _resource_rows(db, req_id)
    return build_observation_summary(item["resource"] for item in resources)


@app.get("/api/requests/{req_id}/fhir")
def request_fhir(req_id: str) -> list[dict]:
    with connection() as db:
        _get_request(db, req_id)
        resources = _resource_rows(db, req_id)
    return [item["resource"] for item in resources]


@app.get("/api/demo/sms")
def sms_outbox() -> list[dict]:
    with connection() as db:
        rows = db.execute("SELECT * FROM notifications WHERE channel='sms' ORDER BY id DESC").fetchall()
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
