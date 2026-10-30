#!/usr/bin/env python3
"""Load the supplied two-date synthetic laboratory examples through DocBinder's public flow."""

from __future__ import annotations

import os
from pathlib import Path
import re

import httpx


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "example-data"
BASE = os.getenv("DOCBINDER_API_URL", "http://localhost:8000")
SEED_REASON_PREFIX = "Example dataset trend: "


def patient_from_report(path: Path) -> tuple[str, str, str]:
    text = path.read_text()
    match = re.search(
        r"^Patient:\s*(.+?)\s+DOB:\s*(\d{4}-\d{2}-\d{2})\s+Demo ID:\s*([A-Za-z0-9.-]+)",
        text,
        re.MULTILINE,
    )
    if not match:
        raise ValueError(f"Unsupported patient header in {path.name}")
    return match.group(3), match.group(1), match.group(2)


def scenarios() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (DATA / "report_manifest.md").read_text().splitlines():
        if not line.startswith("| LAB_"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        patient_id = cells[0].split("_")[1]
        values.setdefault(patient_id, cells[3])
    return values


def main() -> None:
    scenario_by_patient = scenarios()
    with httpx.Client(base_url=BASE, timeout=60) as client:
        existing = client.get("/api/requests", params={"limit": 100})
        existing.raise_for_status()
        seeded = {
            row["patient_id"]: row
            for row in existing.json()
            if row.get("reason", "").startswith(SEED_REASON_PREFIX) and row["status"] == "filed"
        }
        created: list[tuple[str, str]] = []
        for patient_number in range(1, 11):
            patient_id = f"P{patient_number:03d}"
            if patient_id in seeded:
                print(f"SKIP {patient_id}: already filed as {seeded[patient_id]['id']}")
                continue
            reports = sorted(DATA.glob(f"LAB_{patient_id}_*.md"))
            if len(reports) != 2:
                raise RuntimeError(f"Expected two reports for {patient_id}, found {len(reports)}")
            parsed_id, patient_name, birth_date = patient_from_report(reports[0])
            if parsed_id != patient_id:
                raise RuntimeError(f"Patient ID mismatch in {reports[0].name}")
            reason = SEED_REASON_PREFIX + scenario_by_patient[patient_id]
            response = client.post("/api/requests", json={
                "patient_id": patient_id,
                "patient_name": patient_name,
                "patient_birth_date": birth_date,
                "patient_phone": "",
                "recipient_name": "Dr. Eva Brandl",
                "recipient_role": "Laboratory physician at Labor Kanalstraße",
                "channel": "email",
                "contact": "eva.brandl@labor-kanal.example",
                "document_type_code": "laboratory_results",
                "purpose_or_legal_basis": "optimize treatment",
                "reason": reason,
            })
            response.raise_for_status()
            request = response.json()
            token = request["invitation_url"].rsplit("/", 1)[-1]
            client.get(f"/api/invitations/{token}").raise_for_status()
            verified = client.post(
                f"/api/invitations/{token}/verify", json={"full_name": "Eva Brandl"}
            )
            verified.raise_for_status()
            verification_token = verified.json()["verification_token"]
            with reports[0].open("rb") as first, reports[1].open("rb") as second:
                filed = client.post(
                    f"/api/invitations/{token}/submit",
                    headers={"X-Verification-Token": verification_token},
                    data={"patient_name": patient_name, "patient_birth_date": birth_date},
                    files=[
                        ("files", (reports[0].name, first, "text/markdown")),
                        ("files", (reports[1].name, second, "text/markdown")),
                    ],
                )
            filed.raise_for_status()
            created.append((patient_id, request["id"]))
            print(f"FILED {patient_id}: {request['id']}")
    print(f"Done: {len(created)} new example requests filed.")


if __name__ == "__main__":
    main()
