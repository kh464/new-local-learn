from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    redis_url: str = "redis://localhost:6379/0"
    artifacts_dir: Path = Field(default=Path("artifacts"))
    workspace_dir: Path = Field(default=Path("artifacts/workspace"))
    max_file_count: int = 2000
    max_file_bytes: int = 50000
    allowed_github_hosts: tuple[str, ...] = ("github.com", "www.github.com")
