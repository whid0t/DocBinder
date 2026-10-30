from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv("DATABASE_PATH", "/data/carebridge.db"))
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:3000")
    mail_host: str = os.getenv("MAIL_HOST", "mailpit")
    mail_port: int = int(os.getenv("MAIL_PORT", "1025"))
    fhir_base_url: str = os.getenv("FHIR_BASE_URL", "http://hapi-fhir:8080/fhir")
    cors_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if value.strip()
    )


settings = Settings()

