from __future__ import annotations

from email.message import EmailMessage
import smtplib
import sqlite3

from .config import settings
from .db import add_notification, utc_now


def queue_invitation(
    db: sqlite3.Connection,
    *,
    request_id: str,
    channel: str,
    destination: str,
    action_url: str,
) -> None:
    body = (
        f"CareBridge request {request_id}: a healthcare professional has asked you to "
        "respond securely. Patient and document details are available only after identity "
        "verification."
    )
    notification_id = add_notification(
        db,
        request_id=request_id,
        audience="external_professional",
        channel=channel,
        destination=destination,
        subject="Secure CareBridge request",
        body=body,
        action_url=action_url,
    )
    if channel == "email":
        message = EmailMessage()
        message["From"] = "no-reply@carebridge.local"
        message["To"] = destination
        message["Subject"] = "Secure CareBridge request"
        message.set_content(f"{body}\n\nOpen securely: {action_url}\n")
        try:
            with smtplib.SMTP(settings.mail_host, settings.mail_port, timeout=3) as smtp:
                smtp.send_message(message)
            db.execute(
                "UPDATE notifications SET status='delivered', delivered_at=? WHERE id=?",
                (utc_now(), notification_id),
            )
        except OSError:
            # Keep it queued: Mailpit may not be running during unit/API development.
            pass


def queue_patient_notice(
    db: sqlite3.Connection, request_id: str, destination: str, doctor: str
) -> None:
    add_notification(
        db,
        request_id=request_id,
        audience="patient",
        channel="sms",
        destination=destination,
        body=(
            f"Klinikum Beispielstadt ({doctor}) initiated healthcare document request "
            f"{request_id}. This is an informational notice, not a consent request."
        ),
        status="simulated",
    )


def queue_doctor_notice(db: sqlite3.Connection, request: sqlite3.Row, body: str) -> None:
    add_notification(
        db,
        request_id=request["id"],
        audience="doctor",
        channel="matrix",
        destination=request["matrix_room_id"] or request["requesting_user_id"],
        body=body,
        status="queued",
    )

