"""Settings for the document-service.

Reads from process env at import time; defaults match .env.example so a
developer can run pytest without exporting anything. The JWT secret + issuer
mirror auth-service: document-service only DECODES access tokens.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+asyncpg://maiplot:change-me-local@localhost:5432/maiplot"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_issuer: str = "maiplot-platform"

    # Listing legal documents (SCRUM-23) are PRIVATE — stored in the documents
    # bucket and served only via short-TTL pre-signed URLs (never public).
    # In-memory fake storage is the default so local/CI never reach S3.
    doc_storage_use_fake: bool = True
    doc_s3_bucket: str = "maiplot-documents-local"
    doc_s3_region: str = "af-south-1"
    doc_s3_endpoint_url: str = ""
    doc_presign_ttl_seconds: int = 900
    max_document_bytes: int = 10 * 1024 * 1024

    # Watermarking (CLAUDE.md): a buyer-name + timestamp overlay is applied
    # before a document is served to a buyer. The fake watermarker is the
    # default so CI needs no image/PDF libraries at runtime.
    watermark_use_fake: bool = True

    # Admin (legal team) endpoints require admin JWT AND an IP whitelist
    # (CLAUDE.md). Kong enforces the allowlist at the edge; this app-level
    # check is defence in depth. Comma-separated IPs; empty = allow any
    # (dev/test default).
    admin_ip_allowlist: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
