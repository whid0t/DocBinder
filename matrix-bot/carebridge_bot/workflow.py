from __future__ import annotations

STEPS = [
    "recipient", "role", "channel", "contact", "document_type", "legal_basis", "reason", "confirm"
]
LEGAL = {
    "1": ("patient_consent_recorded", "Patient consent recorded"),
    "2": ("necessary_for_treatment", "Necessary for treatment"),
    "3": ("other_documented_legal_basis", "Other documented legal basis"),
}


def first_prompt() -> str:
    return (
        "Let's create a secure document request for **Maria Beispiel (12 March 1961)**.\n\n"
        "Who should provide the document?\n"
        "1. Dr. Eva Brandl (lab)\n2. Stefan Kern (rehabilitation)\n\n"
        "Reply with **1** or **2**. Send `!cancel` at any time."
    )


def advance(step: str, text: str, data: dict) -> tuple[str, dict, str]:
    value = text.strip()
    if not value:
        return step, data, "Please enter a value, or send `!cancel`."
    if step == "recipient":
        if value == "1":
            data.update(recipient_name="Dr. Eva Brandl", expected_identity_id="AT-EID-EVA-BRANDL")
        elif value == "2":
            data.update(recipient_name="Stefan Kern", expected_identity_id="AT-EID-STEFAN-KERN")
        else:
            return step, data, "Reply **1** for Dr. Eva Brandl or **2** for Stefan Kern."
        return "role", data, "What is the recipient's role?"
    if step == "role":
        data["recipient_role"] = value
        return "channel", data, "Delivery channel? Reply **email** or **sms**."
    if step == "channel":
        channel = value.casefold()
        if channel not in {"email", "sms"}:
            return step, data, "Reply **email** or **sms**."
        data["channel"] = channel
        return "contact", data, f"Enter the recipient's {channel} address."
    if step == "contact":
        if data["channel"] == "email" and ("@" not in value or "." not in value.rsplit("@", 1)[-1]):
            return step, data, "That email address looks incomplete. Include `@` and the domain."
        data["contact"] = value
        warning = "\n\n⚠️ Please double-check this unusual domain." if value.casefold().endswith(".con") else ""
        return "document_type", data, f"What document should be requested?{warning}"
    if step == "document_type":
        data["document_type"] = value
        return "legal_basis", data, (
            "Select the legal basis:\n1. Patient consent recorded\n"
            "2. Necessary for treatment\n3. Other documented legal basis"
        )
    if step == "legal_basis":
        if value not in LEGAL:
            return step, data, "Reply **1**, **2**, or **3**."
        data["legal_basis"], data["legal_basis_label"] = LEGAL[value]
        return "reason", data, "Briefly state why this document is required. This is retained in the audit log."
    if step == "reason":
        if len(value) < 3:
            return step, data, "Please provide a short, meaningful reason."
        data["reason"] = value
        summary = (
            "**Review the request**\n\n"
            "- Patient: Maria Beispiel (12 March 1961)\n"
            f"- Recipient: {data['recipient_name']}, {data['recipient_role']}\n"
            f"- Delivery: {data['channel']} — {data['contact']}\n"
            f"- Document: {data['document_type']}\n"
            f"- Legal basis: {data['legal_basis_label']}\n"
            f"- Reason: {data['reason']}\n\n"
            "Reply **confirm** to send, or `!cancel`."
        )
        return "confirm", data, summary
    return step, data, "Reply **confirm** to send, or `!cancel`."


def backend_payload(room_id: str, user_id: str, data: dict) -> dict:
    return {
        "matrix_room_id": room_id,
        "requesting_user_id": user_id,
        "patient_id": "maria-beispiel",
        "patient_display": "Maria Beispiel",
        "patient_birth_date": "1961-03-12",
        "patient_phone": "+43 660 000 0199",
        "recipient_name": data["recipient_name"],
        "recipient_role": data["recipient_role"],
        "expected_identity_id": data["expected_identity_id"],
        "channel": data["channel"],
        "contact": data["contact"],
        "document_type": data["document_type"],
        "legal_basis": data["legal_basis"],
        "reason": data["reason"],
    }

