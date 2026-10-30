from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re


MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}
ALLOWED_LOINC = {"6301-6", "14979-9", "777-3", "3255-7"}

# UCUM requires '*' for exponentiation; the documents use '^'.
UCUM_UNIT_MAP = {
    "10^9/L": "10*9/L",
    "10^12/L": "10*12/L",
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
    match = re.search(
        r"^Patient:\s*(.+?),\s*born\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*$",
        text,
        flags=re.MULTILINE,
    )
    if not match or match.group(3) not in MONTHS:
        raise ParseError("The document needs a 'Patient: Name, born D Month YYYY' line.")
    birth = datetime(int(match.group(4)), MONTHS[match.group(3)], int(match.group(2)))
    return PatientHeader(match.group(1).strip(), birth.date().isoformat())


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
        if not line.startswith("|") or "---" in line or "LOINC code" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 5:
            continue
        name, result, unit, reference, loinc = cells
        if loinc not in ALLOWED_LOINC:
            raise ParseError(f"Unsupported or missing LOINC code: {loinc}")
        try:
            numeric_result = float(result)
        except ValueError as exc:
            raise ParseError(f"Result for {name} must be numeric.") from exc
        rows.append({
            "name": name,
            "value": numeric_result,
            "unit": unit,            # original display unit (or "1" if empty)
            "ucum_code": UCUM_UNIT_MAP.get(unit, unit),   # corrected UCUM code
            "reference": reference,
            "loinc": loinc,
        })
    if not rows:
        raise ParseError("No supported laboratory result table was found.")
    return rows


def parse_author(text: str, prefix: str) -> str | None:
    match = re.search(rf"^{re.escape(prefix)}:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None

