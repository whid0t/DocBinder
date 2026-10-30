from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re
from zoneinfo import ZoneInfo


MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}
LOINC_RE = re.compile(r"^\d{1,5}-\d$")

# UCUM requires '*' for exponentiation; the documents use '^'.
UCUM_UNIT_MAP = {
    "10^9/L": "10*9/L",
    "10^12/L": "10*12/L",
}

# Deterministic conversions needed by the supplied synthetic example dataset.
# The original value/unit remain available on the parsed row for provenance notes.
CANONICAL_CONVERSIONS = {
    ("1558-6", "mmol/L"): ("mg/dL", "mg/dL", lambda value: round(value * 18.0182)),
    ("2160-0", "umol/L"): ("mg/dL", "mg/dL", lambda value: round(value / 88.4, 2)),
    ("2160-0", "µmol/L"): ("mg/dL", "mg/dL", lambda value: round(value / 88.4, 2)),
}

class ParseError(ValueError):
    pass


class PatientMismatch(ParseError):
    pass


@dataclass(frozen=True)
class PatientHeader:
    name: str
    birth_date: str


def parse_patient(text: str) -> PatientHeader:
    original_match = re.search(
        r"^Patient:\s*(.+?),\s*born\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*$",
        text,
        flags=re.MULTILINE,
    )
    if original_match:
        if original_match.group(3) not in MONTHS:
            raise ParseError("The patient birth date uses an unsupported month.")
        try:
            birth = datetime(
                int(original_match.group(4)), MONTHS[original_match.group(3)],
                int(original_match.group(2)),
            ).date()
        except ValueError as exc:
            raise ParseError("The patient birth date is not a valid calendar date.") from exc
        return PatientHeader(original_match.group(1).strip(), birth.isoformat())

    example_match = re.search(
        r"^Patient:\s*(.+?)\s+DOB:\s*(\d{4}-\d{2}-\d{2})(?:\s+Demo ID:\s*[A-Za-z0-9.-]+)?\s*$",
        text,
        flags=re.MULTILINE,
    )
    if not example_match:
        raise ParseError(
            "The document needs a supported patient header with name and birth date."
        )
    try:
        birth = datetime.strptime(example_match.group(2), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ParseError("The patient birth date is not a valid calendar date.") from exc
    return PatientHeader(example_match.group(1).strip(), birth.isoformat())


def assert_patient(text: str, expected_name: str, expected_birth_date: str) -> PatientHeader:
    patient = parse_patient(text)
    if patient.name.casefold() != expected_name.casefold() or patient.birth_date != expected_birth_date:
        raise PatientMismatch(
            f"Document patient {patient.name} ({patient.birth_date}) does not match the request."
        )
    return patient


def parse_lab_rows(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 5:
            raise ParseError("Every laboratory table row must contain exactly five columns.")
        name, result, unit, reference, loinc = cells
        if name.casefold() == "test" and loinc.casefold() in {"loinc", "loinc code"}:
            continue
        if not LOINC_RE.fullmatch(loinc):
            raise ParseError(f"Invalid or missing LOINC code: {loinc}")
        if result.casefold() == "not reported":
            continue
        try:
            numeric_result = float(result)
        except ValueError as exc:
            raise ParseError(f"Result for {name} must be numeric.") from exc
        if not math.isfinite(numeric_result):
            raise ParseError(f"Result for {name} must be a finite number.")
        raw_value, raw_unit = numeric_result, unit or "1"
        conversion = CANONICAL_CONVERSIONS.get((loinc, raw_unit))
        if conversion:
            unit, ucum_code, converter = conversion
            numeric_result = converter(numeric_result)
        else:
            unit = raw_unit
            ucum_code = UCUM_UNIT_MAP.get(unit, unit)
        rows.append({
            "name": name,
            "value": numeric_result,
            "unit": unit,
            "ucum_code": ucum_code,
            "raw_value": raw_value,
            "raw_unit": raw_unit,
            "normalized": conversion is not None,
            "reference": reference,
            "loinc": loinc,
        })
    if not rows:
        raise ParseError("No supported laboratory result table was found.")
    return rows


def parse_lab_timestamps(text: str) -> tuple[str, str | None]:
    sample = _parse_document_datetime(text, "Sample taken", required=True)
    reported = _parse_document_datetime(text, "Reported", required=False)
    return sample, reported


def _parse_document_datetime(text: str, label: str, *, required: bool) -> str | None:
    match = re.search(
        rf"(?:^|\s){re.escape(label)}:\s*(.+?)(?=\s+(?:Sample taken|Reported):|$)",
        text,
        flags=re.MULTILINE,
    )
    if not match:
        if required:
            raise ParseError(f"The laboratory document needs a '{label}' timestamp.")
        return None
    value = match.group(1).strip()
    parsed = None
    for date_format in ("%d %B %Y, %H:%M", "%Y-%m-%d, %H:%M"):
        try:
            parsed = datetime.strptime(value, date_format)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ParseError(f"The '{label}' timestamp is invalid.")
    return parsed.replace(tzinfo=ZoneInfo("Europe/Vienna")).isoformat()


def is_laboratory_document(text: str) -> bool:
    has_loinc_header = bool(re.search(r"\|\s*LOINC(?: code)?\s*\|", text, re.IGNORECASE))
    return has_loinc_header and bool(re.search(r"^Sample taken:", text, re.MULTILINE))


def is_rehabilitation_document(text: str) -> bool:
    return bool(re.search(r"^Written by:", text, re.MULTILINE)) and "discharge report" in text.casefold()


def parse_author(text: str, prefix: str) -> str | None:
    match = re.search(rf"^{re.escape(prefix)}:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None

