from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BFL_EU_HOST = "api.eu.bfl.ai"


def _env_files() -> tuple[str, ...]:
    # Local monorepo: apps/api/kitframe/settings.py → repo root .env (parents[3]).
    # Docker image layout is /app/kitframe/settings.py — only parents[0..1] exist.
    here = Path(__file__).resolve()
    candidates: list[Path] = [Path(".env")]
    try:
        candidates.insert(0, here.parents[3] / ".env")
    except IndexError:
        pass
    for parent in here.parents:
        candidates.append(parent / ".env")
    existing = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            existing.append(key)
    return tuple(existing) if existing else (".env",)


_ENV_FILES = _env_files()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8080"
    database_url: str = "postgresql+asyncpg://kitframe:kitframe@localhost:5433/kitframe"
    s3_endpoint: str | None = Field(
        default="http://localhost:9000",
        validation_alias=AliasChoices("S3_ENDPOINT", "AWS_S3_ENDPOINT"),
    )
    s3_region: str = Field(
        default="eu-west-1",
        validation_alias=AliasChoices("S3_REGION", "AWS_REGION"),
    )
    s3_bucket: str = Field(
        default="kitframe-assets",
        validation_alias=AliasChoices("S3_BUCKET", "AWS_PRIVATE_BUCKET_NAME", "AWS_PUBLIC_BUCKET_NAME"),
    )
    s3_access_key_id: str = Field(
        default="kitframe",
        validation_alias=AliasChoices("S3_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"),
    )
    s3_secret_access_key: str = Field(
        default="kitframekitframe",
        validation_alias=AliasChoices("S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"),
    )
    s3_use_path_style: bool = True
    # All object keys are stored under this prefix (shared-bucket isolation).
    s3_key_prefix: str = Field(default="kitframe", validation_alias=AliasChoices("S3_KEY_PREFIX"))
    jwt_secret: str = Field(min_length=32, default="local-dev-jwt-secret-change-me-now!!")
    app_encryption_key: str = Field(
        default="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    )  # 32 bytes base64 for local only
    image_provider: str = "fake"
    image_provider_model: str = "fake-v1"
    bfl_api_key: str = ""
    bfl_api_base_url: str = "https://api.eu.bfl.ai/v1"
    llm_provider: str = "fake"
    llm_provider_model: str = "fake-llm"
    mistral_api_key: str = ""
    mistral_api_base_url: str = "https://api.mistral.ai/v1"
    smtp_host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("SMTP_HOST", "EMAIL_SERVER_HOST"),
    )
    smtp_port: int = Field(
        default=1025,
        validation_alias=AliasChoices("SMTP_PORT", "EMAIL_SERVER_PORT"),
    )
    smtp_user: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_USER", "EMAIL_SERVER_USER"),
    )
    smtp_password: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_PASSWORD", "EMAIL_SERVER_PASS"),
    )
    smtp_use_tls: bool = True
    email_from: str = Field(
        default="Kitframe <noreply@kitframe.local>",
        validation_alias=AliasChoices("EMAIL_FROM"),
    )
    shopify_api_version: str = "2025-01"
    sentry_dsn_api: str = ""
    metrics_token: str = "local-metrics-token"
    worker_concurrency: int = 4
    cors_origins: str = "http://localhost:3000"
    seed_passwords: bool = True

    @field_validator("s3_endpoint", mode="before")
    @classmethod
    def empty_endpoint_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://") and "+asyncpg" not in value:
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod_like(self) -> bool:
        return self.app_env in ("staging", "production")

    @property
    def uses_aws_s3(self) -> bool:
        return self.s3_endpoint is None

    def validate_providers(self) -> None:
        if self.is_prod_like:
            if self.image_provider == "fake" or self.llm_provider == "fake":
                raise RuntimeError("fake providers are not allowed in staging/production")
            if self.image_provider == "bfl":
                host = urlparse(self.bfl_api_base_url).hostname or ""
                if host != BFL_EU_HOST:
                    raise RuntimeError(
                        f"BFL host must be {BFL_EU_HOST} in staging/production, got {host!r}"
                    )
                if not self.bfl_api_key:
                    raise RuntimeError("BFL_API_KEY is required when IMAGE_PROVIDER=bfl")
            if self.llm_provider == "mistral" and not self.mistral_api_key:
                raise RuntimeError("MISTRAL_API_KEY is required when LLM_PROVIDER=mistral")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_providers()
    return settings
