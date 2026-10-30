from docbinder_bot.workflow import LAB_EXAMPLE, backend_payload, parse_request_block


def test_complete_single_message_workflow():
    data, message = parse_request_block(LAB_EXAMPLE)
    assert data is not None
    assert "Review the DocBinder request" in message
    payload = backend_payload("!room:klinikum.example", "@lena.hofer:klinikum.example", data)
    assert payload["patient_id"] == "maria-beispiel"
    assert payload["purpose_or_legal_basis"] == "necessary for treatment"
    assert payload["document_type_code"] == "laboratory_results"


def test_missing_and_unknown_fields_are_reported_together():
    data, message = parse_request_block("patient_id: maria\nmade_up: value")
    assert data is None
    assert "unknown field `made_up`" in message
    assert "missing:" in message


def test_invalid_email_is_visual_validation_only():
    data, message = parse_request_block(LAB_EXAMPLE.replace(
        "eva.brandl@labor-kanal.example", "missing-at"
    ))
    assert data is None
    assert "looks incomplete" in message


def test_con_domain_warns_but_accepts():
    data, message = parse_request_block(LAB_EXAMPLE.replace(
        "eva.brandl@labor-kanal.example", "eva@example.con"
    ))
    assert data is not None
    assert "double-check" in message
