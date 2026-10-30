from __future__ import annotations

import base64
from datetime import datetime, timezone
import uuid

from .parser import parse_author, parse_lab_rows, parse_lab_timestamps


# Official LOINC display names, as reported by the HL7 validator. Coding.display must
# match the code system exactly, so codes not listed here are filed without a display
# and keep the lab's own wording in CodeableConcept.text.
LOINC_DISPLAY = {
    "6301-6": "INR in Platelet poor plasma by Coagulation assay",
    "3255-7": "Fibrinogen [Mass/volume] in Platelet poor plasma by Coagulation assay",
    "777-3": "Platelets [#/volume] in Blood by Automated count",
    "14979-9": "aPTT in Platelet poor plasma by Coagulation assay",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_lab_resources(
    text: str, patient_id: str, submitter_name: str, identity_id: str
) -> list[dict]:
    resources: list[dict] = []
    targets: list[dict] = []
    effective, issued = parse_lab_timestamps(text)
    validator = parse_author(text, "Validated by")
    for row in parse_lab_rows(text):
        resource_id = str(uuid.uuid4())
        notes = [{"text": f"Reference range: {row['reference']}"}]
        if row.get("normalized"):
            notes.append({
                "text": f"Source value: {row['raw_value']} {row['raw_unit']}; normalized deterministically for comparison."
            })
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
                **({"display": LOINC_DISPLAY[row["loinc"]]} if row["loinc"] in LOINC_DISPLAY else {}),
            }], "text": row["name"]},
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": effective,
            "valueQuantity": {
                "value": row["value"],
                "unit": row["unit"],               # display
                "system": "http://unitsofmeasure.org",
                "code": row.get("ucum_code", row["unit"]),   # UCUM code
            },
            "note": notes,
        }
        if issued:
            observation["issued"] = issued
        if validator:
            observation["performer"] = [{"display": validator}]
        resources.append(observation)
        targets.append({"reference": f"Observation/{resource_id}"})
    resources.append(_provenance(targets, submitter_name, identity_id, validator))
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
        "who": {
            "display": submitter,
            "identifier": {
                "system": "urn:docbinder:simulated-name-match",
                "value": identity_id,
            },
        },
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
        "policy": ["urn:docbinder:identity:simulated-name-match"],
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

