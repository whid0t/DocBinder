"""Run inside the backend container against the live Compose stack."""

from pathlib import Path
import sys

import httpx


BASE = "http://localhost:8000"


def create() -> tuple[str, str]:
    response = httpx.post(f"{BASE}/api/requests", json={
        "recipient_name": "Dr. Eva Brandl",
        "recipient_role": "Lab physician",
        "patient_name": "Maria Beispiel",
        "channel": "email",
        "contact": "eva.brandl@labor-kanal.example",
        "document_type_code": "laboratory_results",
        "purpose_or_legal_basis": "necessary for treatment",
        "reason": "Integration smoke test",
    }, timeout=10)
    response.raise_for_status()
    data = response.json()
    return data["id"], data["invitation_url"].rsplit("/", 1)[-1]


def verify(token: str) -> str:
    opened = httpx.get(f"{BASE}/api/invitations/{token}", timeout=10)
    opened.raise_for_status()
    checked = httpx.post(
        f"{BASE}/api/invitations/{token}/verify",
        json={"full_name": "Eva Brandl"},
        timeout=10,
    )
    checked.raise_for_status()
    return checked.json()["verification_token"]


def submit(token: str, verification: str, document: str) -> httpx.Response:
    text = Path(f"/scenario/documents/{document}").read_text()
    return httpx.post(
        f"{BASE}/api/invitations/{token}/submit",
        headers={"X-Verification-Token": verification},
        data={
            "patient_name": "Maria Beispiel",
            "patient_birth_date": "1961-03-12",
            "markdown": text,
        },
        timeout=40,
    )


def submit_longitudinal_batch(token: str, verification: str) -> httpx.Response:
    first = Path("/scenario/documents/lab-result-maria-beispiel.md").read_text()
    second = first.replace("22 October 2026", "29 October 2026").replace(
        "| INR (prothrombin time) | 1.0 |", "| INR (prothrombin time) | 1.1 |"
    )
    return httpx.post(
        f"{BASE}/api/invitations/{token}/submit",
        headers={"X-Verification-Token": verification},
        data={"patient_name": "Maria Beispiel", "patient_birth_date": "1961-03-12"},
        files=[
            ("files", ("lab-day-x.md", first, "text/markdown")),
            ("files", ("lab-day-y.md", second, "text/markdown")),
        ],
        timeout=40,
    )


def main() -> None:
    good_id, good_token = create()
    filed = submit_longitudinal_batch(good_token, verify(good_token))
    filed.raise_for_status()
    assert filed.json()["documents"] == 2
    assert filed.json()["resources"] == 10
    fhir = httpx.get(f"{BASE}/api/requests/{good_id}/fhir", timeout=10)
    fhir.raise_for_status()
    assert len(fhir.json()) == 10
    summary = httpx.get(f"{BASE}/api/requests/{good_id}/summary", timeout=10)
    summary.raise_for_status()
    inr = next(group for group in summary.json()["groups"] if group["loinc"] == "6301-6")
    assert [reading["value"] for reading in inr["readings"]] == [1.0, 1.1]

    wrong_id, wrong_token = create()
    rejected = submit(wrong_token, verify(wrong_token), "lab-result-max-beispiel.md")
    assert rejected.status_code == 409, rejected.text
    audit = httpx.get(f"{BASE}/api/requests/{wrong_id}/audit", timeout=10)
    audit.raise_for_status()
    assert "misdelivery_caught" in {event["event_type"] for event in audit.json()}
    print(f"OK: filed {good_id}; rejected wrong-patient request {wrong_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise
