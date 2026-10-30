from __future__ import annotations

from datetime import date
import re


DOCUMENT_TYPES = {"laboratory_results", "rehabilitation_report"}
PURPOSES = {"necessary for treatment", "transfer of patient", "optimize treatment"}
REQUIRED_FIELDS = (
    "patient_id", "patient_name", "patient_birth_date", "recipient_name",
    "recipient_role", "channel", "contact", "document_type",
    "purpose_or_legal_basis", "reason",
)
OPTIONAL_FIELDS = {"patient_phone"}
PATIENT_ID_RE = re.compile(r"^[A-Za-z0-9.-]{1,64}$")

LAB_EXAMPLE = """patient_id: maria-beispiel
patient_name: Maria Beispiel
patient_birth_date: 1961-03-12
patient_phone: +43 660 000 0199
recipient_name: Dr. Eva Brandl
recipient_role: Lab physician at Labor Kanalstraße
channel: email
contact: eva.brandl@labor-kanal.example
document_type: laboratory_results
purpose_or_legal_basis: necessary for treatment
reason: Latest blood clotting results before a planned procedure"""

REHAB_EXAMPLE = """patient_id: maria-beispiel
patient_name: Maria Beispiel
patient_birth_date: 1961-03-12
patient_phone: +43 660 000 0199
recipient_name: Stefan Kern
recipient_role: Discharge manager at Reha Waldblick
channel: sms
contact: +43 660 000 0101
document_type: rehabilitation_report
purpose_or_legal_basis: transfer of patient
reason: Rehabilitation discharge report for continued treatment"""


def help_text() -> str:
    return (
        "**DocBinder request format**\n\nPaste all fields in one message, then review and confirm. "
        "Names and patients may be changed for synthetic demo cases.\n\n"
        f"**Laboratory example**\n```\n{LAB_EXAMPLE}\n```\n\n"
        f"**Rehabilitation example**\n```\n{REHAB_EXAMPLE}\n```\n\n"
        "Document type must be `laboratory_results` or `rehabilitation_report`.\n"
        "Purpose must be `necessary for treatment`, `transfer of patient`, or `optimize treatment`.\n"
        "Send `!cancel` at any time."
    )


def parse_request_block(text: str) -> tuple[dict | None, str]:
    data: dict[str, str] = {}
    errors: list[str] = []
    allowed = set(REQUIRED_FIELDS) | OPTIONAL_FIELDS
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        if ":" not in line:
            errors.append(f"line {number} must use `field: value`")
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.casefold()
        if key not in allowed:
            errors.append(f"unknown field `{key}`")
        elif key in data:
            errors.append(f"duplicate field `{key}`")
        elif not value:
            errors.append(f"`{key}` cannot be empty")
        else:
            data[key] = value

    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        errors.append("missing: " + ", ".join(f"`{field}`" for field in missing))
    if data.get("patient_id") and not PATIENT_ID_RE.fullmatch(data["patient_id"]):
        errors.append("`patient_id` may contain only letters, digits, periods, and hyphens")
    if data.get("patient_birth_date"):
        try:
            date.fromisoformat(data["patient_birth_date"])
        except ValueError:
            errors.append("`patient_birth_date` must be a valid YYYY-MM-DD date")
    if data.get("channel", "").casefold() not in {"email", "sms"}:
        errors.append("`channel` must be email or sms")
    elif data.get("channel", "").casefold() == "email":
        contact = data.get("contact", "")
        if "@" not in contact or "." not in contact.rsplit("@", 1)[-1]:
            errors.append("the email address looks incomplete")
    if data.get("document_type", "").casefold() not in DOCUMENT_TYPES:
        errors.append("`document_type` must be laboratory_results or rehabilitation_report")
    if data.get("purpose_or_legal_basis", "").casefold() not in PURPOSES:
        errors.append("`purpose_or_legal_basis` is not one of the three supported options")
    if errors:
        return None, "Please correct the block:\n- " + "\n- ".join(errors) + "\n\nSend `!help` for examples."

    data["channel"] = data["channel"].casefold()
    data["document_type"] = data["document_type"].casefold()
    data["purpose_or_legal_basis"] = data["purpose_or_legal_basis"].casefold()
    warning = "\n\n⚠️ Visually double-check the `.con` email domain." if data.get("contact", "").casefold().endswith(".con") else ""
    review = (
        "**Review the DocBinder request**\n\n"
        f"- Patient: {data['patient_name']} ({data['patient_birth_date']}, ID `{data['patient_id']}`)\n"
        f"- Recipient: {data['recipient_name']}, {data['recipient_role']}\n"
        f"- Delivery: {data['channel']} — {data['contact']}\n"
        f"- Document: {data['document_type']}\n"
        f"- Purpose / legal basis: {data['purpose_or_legal_basis']}\n"
        f"- Reason: {data['reason']}\n\n"
        "Reply **confirm** to create it, or `!cancel`." + warning
    )
    return data, review


def backend_payload(room_id: str, user_id: str, data: dict) -> dict:
    return {
        "matrix_room_id": room_id,
        "requesting_user_id": user_id,
        "patient_id": data["patient_id"],
        "patient_name": data["patient_name"],
        "patient_birth_date": data["patient_birth_date"],
        "patient_phone": data.get("patient_phone", ""),
        "recipient_name": data["recipient_name"],
        "recipient_role": data["recipient_role"],
        "channel": data["channel"],
        "contact": data["contact"],
        "document_type_code": data["document_type"],
        "purpose_or_legal_basis": data["purpose_or_legal_basis"],
        "reason": data["reason"],
    }
