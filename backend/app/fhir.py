from __future__ import annotations

import base64
from datetime import datetime, timezone
import uuid

from .parser import parse_author, parse_lab_rows


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_lab_resources(
    text: str, patient_id: str, submitter_name: str, identity_id: str
) -> list[dict]:
    resources: list[dict] = []
    targets: list[dict] = []
    for row in parse_lab_rows(text):
        resource_id = str(uuid.uuid4())
        observation = {
            "resourceType": "Observation",
            "id": resource_id,
            "status": "final",
            "category": [{"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "laboratory",
                "display": "Laboratory",
            }]}],
            "code": {"coding": [{
                "system": "http://loinc.org",
                "code": row["loinc"],
                "display": row["name"],
            }], "text": row["name"]},
            "subject": {"reference": f"Patient/{patient_id}"},
            "valueQuantity": {
                "value": row["value"],
                "unit": row["unit"],
                "system": "http://unitsofmeasure.org",
                "code": row["unit"],
            },
            "note": [{"text": f"Reference range: {row['reference']}"}],
        }
        resources.append(observation)
        targets.append({"reference": f"Observation/{resource_id}"})
    resources.append(_provenance(targets, submitter_name, identity_id, parse_author(text, "Validated by")))
    return resources


def build_rehab_resources(
    text: str, patient_id: str, submitter_name: str, identity_id: str
) -> list[dict]:
    document_id = str(uuid.uuid4())
    document = {
        "resourceType": "DocumentReference",
        "id": document_id,
        "status": "current",
        "type": {"coding": [{
            "system": "http://loinc.org",
            "code": "18842-5",
            "display": "Discharge summary",
        }]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "date": _now(),
        "author": [{"display": parse_author(text, "Written by") or "Unknown document author"}],
        "content": [{"attachment": {
            "contentType": "text/markdown",
            "data": base64.b64encode(text.encode()).decode(),
            "title": "Rehabilitation discharge report",
        }}],
    }
    provenance = _provenance(
        [{"reference": f"DocumentReference/{document_id}"}],
        submitter_name,
        identity_id,
        parse_author(text, "Written by"),
    )
    return [document, provenance]


def _provenance(targets: list[dict], submitter: str, identity_id: str, author: str | None) -> dict:
    agents = [{
        "type": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
            "code": "enterer",
        }]},
        "who": {"display": submitter},
        "onBehalfOf": {"display": f"Identity verified using simulated ID Austria ({identity_id})"},
    }]
    if author:
        agents.append({
            "type": {"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                "code": "author",
            }]},
            "who": {"display": author},
        })
    return {
        "resourceType": "Provenance",
        "id": str(uuid.uuid4()),
        "target": targets,
        "recorded": _now(),
        "activity": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation",
            "code": "CREATE",
        }]},
        "agent": agents,
    }


def transaction_bundle(resources: list[dict]) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [{
            "fullUrl": f"urn:uuid:{resource['id']}",
            "resource": resource,
            "request": {"method": "PUT", "url": f"{resource['resourceType']}/{resource['id']}"},
        } for resource in resources],
    }

