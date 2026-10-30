from dataclasses import dataclass
import re


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@.]+$")


@dataclass(frozen=True)
class EmailResult:
    normalized: str
    warnings: tuple[str, ...]


def validate_email(value: str) -> EmailResult:
    value = value.strip()
    if not EMAIL_RE.fullmatch(value):
        raise ValueError("Enter a complete email address, including @ and a domain.")
    local, domain = value.rsplit("@", 1)
    warnings: list[str] = []
    if domain.endswith(".con"):
        warnings.append("This address ends in .con. Check whether you meant .com.")
    if any(character.isupper() for character in domain):
        warnings.append("The domain contains uppercase characters. Check for a typing error.")
    return EmailResult(f"{local}@{domain.lower()}", tuple(warnings))

