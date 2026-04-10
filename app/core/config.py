from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings import NoDecode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", validate_assignment=True)

    redis_url: str = "redis://localhost:6379/0"
    artifacts_dir: Path = Field(default=Path("artifacts"))
    workspace_dir: Path = Field(default=Path("artifacts/workspace"))
    max_file_count: int = 2000
    max_file_bytes: int = 50000
    max_total_bytes: int = 2_000_000
    allowed_github_hosts: Annotated[tuple[str, ...], NoDecode] = ("github.com", "www.github.com")
    cors_allowed_origins: Annotated[tuple[str, ...], NoDecode] = ()
    api_keys: Annotated[tuple[str, ...], NoDecode] = ()
    api_key_records: Annotated[tuple[str, ...], NoDecode] = ()
    oidc_issuer_url: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_scope_claim: str = "scope"
    oidc_subject_claim: str = "sub"
    oidc_algorithms: Annotated[tuple[str, ...], NoDecode] = ("RS256",)
    oidc_jwks_cache_seconds: int = 300
    clone_timeout_seconds: int = 60
    stream_poll_interval_seconds: float = 0.1
    worker_job_timeout_seconds: int = 300
    worker_max_jobs: int = 10
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 10
    audit_max_events: int = 1000
    request_log_enabled: bool = True
    log_level: str = "INFO"
    task_ttl_seconds: int = 86400
    artifact_ttl_seconds: int = 86400
    llm_enabled: bool = True
    llm_config_path: Path = Field(default=Path("config/llm.yaml"))
    llm_profile: str | None = None
    llm_max_prompt_chars: int = 20000
    llm_max_snippet_chars: int = 1200

    @field_validator("allowed_github_hosts", mode="before")
    @classmethod
    def _parse_allowed_github_hosts(cls, value):
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_cors_allowed_origins(cls, value):
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("api_keys", mode="before")
    @classmethod
    def _parse_api_keys(cls, value):
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("api_key_records", mode="before")
    @classmethod
    def _parse_api_key_records(cls, value):
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(";") if part.strip())
        return value

    @field_validator("oidc_algorithms", mode="before")
    @classmethod
    def _parse_oidc_algorithms(cls, value):
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("llm_profile", mode="before")
    @classmethod
    def _normalize_llm_profile(cls, value):
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value
