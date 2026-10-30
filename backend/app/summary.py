from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable


def build_observation_summary(resources: Iterable[dict]) -> dict:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    names: dict[tuple[str, str], str] = {}
    for resource in resources:
        if resource.get("resourceType") != "Observation":
            continue
        coding = next(
            (
                item for item in resource.get("code", {}).get("coding", [])
                if item.get("system") == "http://loinc.org" and item.get("code")
            ),
            None,
        )
        quantity = resource.get("valueQuantity", {})
        effective = resource.get("effectiveDateTime")
        if not coding or quantity.get("value") is None or not effective:
            continue
        unit = quantity.get("unit") or quantity.get("code") or ""
        ucum = quantity.get("code") or unit
        key = (coding["code"], ucum)
        names[key] = coding.get("display") or resource.get("code", {}).get("text") or coding["code"]
        grouped[key].append({
            "date": effective,
            "value": quantity["value"],
            "unit": unit,
        })

    groups: list[dict] = []
    text_lines: list[str] = []
    for (code, ucum), readings in sorted(grouped.items()):
        readings.sort(key=lambda item: item["date"])
        unit = readings[0]["unit"]
        group = {"loinc": code, "name": names[(code, ucum)], "unit": unit, "ucum_code": ucum, "readings": readings}
        groups.append(group)
        values = " → ".join(
            f"{reading['value']} {unit} on {_display_date(reading['date'])}".replace("  ", " ")
            for reading in readings
        )
        text_lines.append(f"{group['name']} (LOINC {code}): {values}.")

    if not groups:
        return {
            "groups": [],
            "text": "No coded laboratory trend is available for this request.",
        }
    return {"groups": groups, "text": "\n".join(text_lines)}


def _display_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return f"{parsed.day} {parsed.strftime('%b %Y')}"
    except ValueError:
        return value
