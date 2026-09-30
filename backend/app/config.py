"""Runtime configuration. Secrets come from the environment, never from the repo."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+psycopg://hub:hub@localhost:15432/hub"
    hub_recruiter_token: str = Field(min_length=8)
    hub_engineer_token: str = Field(min_length=8)
    storage_dir: Path = Path("./var/storage")
    processing_version: int = 1
    job_lease_seconds: int = 60
    job_max_attempts: int = 3
    max_upload_bytes: int = 20 * 1024 * 1024
    embedding_dimensions: int = 1024
    extractor_provider: str = "none"
    embedding_provider: str = "none"
    requirement_provider: str = "deterministic"
    recruiter_email: str = "recruiter@cadence.local"
    engineer_email: str = "engineer@cadence.local"
    # Starting point for the evaluation set. Tune it; do not treat it as a final decision.
    identity_high_confidence: float = 0.85
    identity_relationship_cutoff: float = 0.5
    identity_weight_email: float = 0.50
    identity_weight_phone: float = 0.30
    identity_weight_name: float = 0.20
    identity_weight_dates: float = 0.40
    identity_weight_explicit_version: float = 0.25
    identity_weight_employment: float = 0.15
    identity_weight_education: float = 0.10
    identity_weight_skills: float = 0.10
    identity_weight_semantic: float = 0.15
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "hr-hub@cadence.local"
    demo_company_email: str = "company@localhost"
    mail_destination: str = "smtp"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Finished documents are archived after this many days. Rows are kept.
    retention_days: int = 730
    backup_dir: Path = Path("./var/backups")

    @field_validator("extractor_provider")
    @classmethod
    def extractor_provider_is_known(cls, value: str) -> str:
        if value not in {"none", "deterministic", "bedrock"}:
            raise ValueError("extractor provider must be none, deterministic, or bedrock")
        return value

    @field_validator("requirement_provider")
    @classmethod
    def requirement_provider_is_known(cls, value: str) -> str:
        if value not in {"none", "deterministic", "bedrock"}:
            raise ValueError("requirement provider must be none, deterministic, or bedrock")
        return value

    @field_validator("mail_destination")
    @classmethod
    def mail_destination_is_known(cls, value: str) -> str:
        if value not in {"smtp", "graph", "ses"}:
            raise ValueError("mail destination must be smtp, graph, or ses")
        return value

    @field_validator("embedding_provider")
    @classmethod
    def embedding_provider_is_known(cls, value: str) -> str:
        if value not in {"none", "local", "bedrock"}:
            raise ValueError("embedding provider must be none, local, or bedrock")
        return value

    @field_validator("embedding_dimensions")
    @classmethod
    def embedding_width_is_fixed(cls, value: int) -> int:
        if value != 1024:
            raise ValueError("embedding width is 1024 until a provider is selected")
        return value

    @field_validator("identity_high_confidence", "identity_relationship_cutoff")
    @classmethod
    def confidence_threshold_is_a_fraction(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("identity thresholds must be greater than 0 and at most 1")
        return value

    @field_validator(
        "identity_weight_email",
        "identity_weight_phone",
        "identity_weight_name",
        "identity_weight_dates",
        "identity_weight_explicit_version",
        "identity_weight_employment",
        "identity_weight_education",
        "identity_weight_skills",
        "identity_weight_semantic",
    )
    @classmethod
    def identity_weights_are_not_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("identity weights cannot be negative")
        return value

    @field_validator("retention_days")
    @classmethod
    def retention_period_is_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("retention period must be at least one day")
        return value

    def validate_runtime(self) -> None:
        # Demo tokens are valid only for ENVIRONMENT=local. Every other
        # environment must receive distinct tokens from a secret store.
        if self.environment != "local" and (
            self.hub_recruiter_token.startswith("dev-") or self.hub_engineer_token.startswith("dev-")
        ):
            raise RuntimeError("refusing development tokens outside ENVIRONMENT=local")
        if self.hub_recruiter_token == self.hub_engineer_token:
            raise RuntimeError("recruiter and engineer tokens must differ")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        loaded = Settings()
        loaded.validate_runtime()
        _settings = loaded
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
