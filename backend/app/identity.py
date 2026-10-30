from __future__ import annotations

import re
import unicodedata


TITLE_RE = re.compile(r"^dr\.?\s+", re.IGNORECASE)


def normalize_person_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = " ".join(normalized.split())
    normalized = TITLE_RE.sub("", normalized)
    return normalized.strip()


def names_match(entered: str, expected: str) -> bool:
    entered_normalized = normalize_person_name(entered)
    return bool(entered_normalized) and entered_normalized == normalize_person_name(expected)

