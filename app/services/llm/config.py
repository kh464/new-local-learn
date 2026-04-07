from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, SecretStr


class GenerationConfig(BaseModel):
    temperature: float = 0.7
    top_p: float = 0.95
    max_tokens: int = 4096


class ProviderDefinition(BaseModel):
    enabled: bool = True
    base_url: str
    api_key: SecretStr
    generation: GenerationConfig = Field(default_factory=GenerationConfig)


class ProviderConfig(BaseModel):
    name: str
    base_url: str
    api_key: SecretStr
    generation: GenerationConfig = Field(default_factory=GenerationConfig)


class RoutingProfile(BaseModel):
    provider: str
    model: str


class RuntimeConfig(BaseModel):
    timeout_seconds: int
    max_retries: int
    profile: RoutingProfile
    provider: ProviderConfig


def load_runtime_config(config_path: Path | str, profile_name: str | None = None) -> RuntimeConfig:
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"LLM config file does not exist: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    llm_payload = payload.get("llm") or {}
    profiles = ((llm_payload.get("routing") or {}).get("profiles") or {})
    selected_profile_name = profile_name or llm_payload.get("default_profile")
    if not selected_profile_name:
        raise ValueError("LLM config is missing a default profile.")

    profile_payload = profiles.get(selected_profile_name)
    if profile_payload is None:
        raise ValueError(f"LLM profile '{selected_profile_name}' is not defined.")
    profile = RoutingProfile.model_validate(profile_payload)

    providers = llm_payload.get("providers") or {}
    provider_payload = providers.get(profile.provider)
    if provider_payload is None:
        raise ValueError(f"LLM provider '{profile.provider}' is not defined.")
    provider_definition = ProviderDefinition.model_validate(provider_payload)
    if not provider_definition.enabled:
        raise ValueError(f"LLM provider '{profile.provider}' is disabled.")

    return RuntimeConfig(
        timeout_seconds=int(llm_payload.get("timeout_seconds", 120)),
        max_retries=int(llm_payload.get("max_retries", 2)),
        profile=profile,
        provider=ProviderConfig(
            name=profile.provider,
            base_url=provider_definition.base_url,
            api_key=provider_definition.api_key,
            generation=provider_definition.generation,
        ),
    )
