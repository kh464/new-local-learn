from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    redis_url: str = "redis://localhost:6379/0"
    artifacts_dir: Path = Path("artifacts")
    workspace_dir: Path = Path("workspace")
    max_file_count: int = 2000
    max_file_bytes: int = 5 * 1024 * 1024
    allowed_github_hosts: list[str] = Field(
        default_factory=lambda: ["github.com", "raw.githubusercontent.com"]
    )
