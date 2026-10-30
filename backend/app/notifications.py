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
        f"DocBinder request {request_id}: a healthcare professional has asked you to "
        "respond securely. Patient and document details are available only after identity "
        "verification."
    )
    notification_id = add_notification(
        db,
        request_id=request_id,
        audience="external_professional",
        channel=channel,
        destination=destination,
        subject="Secure DocBinder request",
        body=body,
        action_url=action_url,
    )
    if channel == "email":
        message = EmailMessage()
        message["From"] = "no-reply@docbinder.local"
        message["To"] = destination
        message["Subject"] = "Secure DocBinder request"
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
    db: sqlite3.Connection,
    request_id: str,
    destination: str,
    clinic: str,
    doctor: str,
) -> None:
    add_notification(
        db,
        request_id=request_id,
        audience="patient",
        channel="sms",
        destination=destination,
        body=(
            f"{clinic} ({doctor}) initiated healthcare document request {request_id}. "
            "REPLY WITH 1 TO ACCEPT, 0 TO DECLINE. If an answer is NOT RECEIVED in 6 hours, "
            "you will receive a call to confirm."
        ),
        status="simulated",
    )


def queue_doctor_notice(db: sqlite3.Connection, request: sqlite3.Row, body: str) -> None:
    room_id = request["matrix_room_id"]
    add_notification(
        db,
        request_id=request["id"],
        audience="doctor",
        channel="matrix" if room_id else "dashboard",
        destination=room_id or request["requesting_user_id"],
        body=body,
        status="queued",
    )

