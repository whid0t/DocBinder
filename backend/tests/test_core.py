import os
from pathlib import Path
import tempfile

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")

from app.db import connection, init_db
from app.email_validation import validate_email
from app.fhir import build_lab_resources, build_rehab_resources
from app.parser import PatientMismatch, assert_patient, parse_lab_rows


ROOT = Path(__file__).parents[2]


def fixture(name: str) -> str:
    return (ROOT / "scenario" / "documents" / name).read_text()


def test_email_normalizes_domain_and_warns():
    result = validate_email("Eva@Labor-Kanal.con")
    assert result.normalized == "Eva@labor-kanal.con"
    assert len(result.warnings) == 2


def test_lab_parser_and_fhir_resources():
    text = fixture("lab-result-maria-beispiel.md")
    assert_patient(text, "Maria Beispiel", "1961-03-12")
    assert len(parse_lab_rows(text)) == 4
    resources = build_lab_resources(text, "maria-beispiel", "Dr. Eva Brandl", "AT-EID-EVA-BRANDL")
    assert [resource["resourceType"] for resource in resources].count("Observation") == 4
    assert resources[-1]["resourceType"] == "Provenance"


def test_wrong_patient_is_rejected():
    try:
        assert_patient(fixture("lab-result-max-beispiel.md"), "Maria Beispiel", "1961-03-12")
    except PatientMismatch:
        pass
    else:
        raise AssertionError("wrong patient was accepted")


def test_rehab_keeps_author_and_submitter_distinct():
    resources = build_rehab_resources(
        fixture("rehab-report-maria-beispiel.md"),
        "maria-beispiel",
        "Stefan Kern",
        "AT-EID-STEFAN-KERN",
    )
    assert resources[0]["author"][0]["display"].startswith("Dr. Johanna Leitner")
    assert resources[1]["agent"][0]["who"]["display"] == "Stefan Kern"


def test_database_schema_initializes():
    init_db()
    with connection() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"requests", "audit_events", "notifications", "fhir_resources"} <= tables

