from carebridge_bot.workflow import advance, backend_payload


def test_complete_guided_workflow():
    data = {}
    step, data, _ = advance("recipient", "1", data)
    assert step == "role"
    step, data, _ = advance(step, "Lab physician", data)
    step, data, _ = advance(step, "email", data)
    step, data, _ = advance(step, "eva.brandl@labor-kanal.example", data)
    step, data, _ = advance(step, "Laboratory result", data)
    step, data, _ = advance(step, "2", data)
    step, data, message = advance(step, "Pre-procedure clotting results", data)
    assert step == "confirm"
    assert "Review the request" in message
    payload = backend_payload("!room:klinikum.example", "@lena.hofer:klinikum.example", data)
    assert payload["patient_id"] == "maria-beispiel"
    assert payload["legal_basis"] == "necessary_for_treatment"


def test_invalid_email_does_not_advance():
    step, _, message = advance("contact", "missing-at", {"channel": "email"})
    assert step == "contact"
    assert "incomplete" in message


def test_con_domain_warns_but_advances():
    step, data, message = advance("contact", "eva@example.con", {"channel": "email"})
    assert step == "document_type"
    assert data["contact"] == "eva@example.con"
    assert "double-check" in message

