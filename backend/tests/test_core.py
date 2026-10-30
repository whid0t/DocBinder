import os
from pathlib import Path
import tempfile

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")

from app.db import connection, init_db
from app.email_validation import validate_email
from app.fhir import build_lab_resources, build_rehab_resources
from app.identity import names_match, normalize_person_name
from app.parser import ParseError, PatientMismatch, assert_patient, parse_lab_rows, parse_lab_timestamps
from app.summary import build_observation_summary


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
    assert resources[0]["effectiveDateTime"].startswith("2026-10-22T08:10")
    assert resources[0]["issued"].startswith("2026-10-22T11:40")
    assert resources[0]["performer"][0]["display"].startswith("Dr. Eva Brandl")


def test_name_matching_is_exact_after_documented_normalization():
    assert names_match("  eva   brandl ", "Dr. Eva Brandl")
    assert normalize_person_name("Ｄｒ. Eva Brandl") == "eva brandl"
    assert not names_match("Eva", "Dr. Eva Brandl")
    assert not names_match("Eva Brändl", "Eva Brandl")


def test_malformed_rows_invalid_dates_and_nonfinite_values_are_controlled():
    text = fixture("lab-result-maria-beispiel.md")
    candidates = (
        text.replace("| 777-3 |", "| 777-3 | extra |", 1),
        text.replace("12 March 1961", "31 February 1961"),
        text.replace("| 1.0 |", "| NaN |", 1),
    )
    for candidate in candidates:
        try:
            assert_patient(candidate, "Maria Beispiel", "1961-03-12")
            parse_lab_rows(candidate)
        except ParseError:
            pass
        else:
            raise AssertionError("invalid laboratory document was accepted")


def test_summary_orders_readings_by_clinical_date():
    resources = build_lab_resources(
        fixture("lab-result-maria-beispiel.md"), "maria-beispiel", "Eva Brandl", "eva brandl"
    )
    later = {**resources[0], "id": "later", "effectiveDateTime": "2026-10-29T08:15:00+01:00"}
    later["valueQuantity"] = {**resources[0]["valueQuantity"], "value": 1.2}
    summary = build_observation_summary([later, resources[0]])
    assert [reading["value"] for reading in summary["groups"][0]["readings"]] == [1.0, 1.2]


def test_supplied_example_data_formats_and_normalization():
    example_root = ROOT / "example-data"
    reports = sorted(example_root.glob("LAB_P*.md"))
    assert len(reports) == 20
    observation_count = 0
    for report in reports:
        text = report.read_text()
        patient = report.stem.split("_")[1]
        header = assert_patient(
            text,
            {
                "P001": "Anna Berger", "P002": "Martin Huber", "P003": "Sofia Leitner",
                "P004": "Thomas Gruber", "P005": "Eva Schmid", "P006": "Paul Wagner",
                "P007": "Helga Mayer", "P008": "Leon Fischer", "P009": "Clara Hofer",
                "P010": "Felix Steiner",
            }[patient],
            {
                "P001": "1964-04-09", "P002": "1959-02-15", "P003": "1970-08-21",
                "P004": "1951-07-12", "P005": "1962-05-20", "P006": "1960-11-04",
                "P007": "1955-01-17", "P008": "1968-06-09", "P009": "1979-03-03",
                "P010": "1957-09-01",
            }[patient],
        )
        assert header.name
        sample, reported = parse_lab_timestamps(text)
        assert sample.startswith(report.stem.rsplit("_", 1)[1])
        assert reported is not None
        observation_count += len(parse_lab_rows(text))
    assert observation_count == 158

    normalized = parse_lab_rows((example_root / "LAB_P009_2026-10-22.md").read_text())
    glucose = next(row for row in normalized if row["loinc"] == "1558-6")
    creatinine = next(row for row in normalized if row["loinc"] == "2160-0")
    assert (glucose["value"], glucose["unit"], glucose["raw_value"]) == (118, "mg/dL", 6.55)
    assert (creatinine["value"], creatinine["unit"], creatinine["raw_value"]) == (0.91, "mg/dL", 80.4)


def test_all_example_observations_match_supplied_ground_truth():
    example_root = ROOT / "example-data"
    expected: dict[str, dict[str, tuple[float, str]]] = {}
    for line in (example_root / "extracted_observations_ground_truth.md").read_text().splitlines():
        if not line.startswith("| P"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        report = cells[3].removesuffix(".pdf") + ".md"
        expected.setdefault(report, {})[cells[6]] = (float(cells[9]), cells[10])

    assert sum(len(rows) for rows in expected.values()) == 158
    for report, expected_rows in expected.items():
        parsed = {row["loinc"]: (row["value"], row["unit"]) for row in parse_lab_rows(
            (example_root / report).read_text()
        )}
        assert parsed == expected_rows, report


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

