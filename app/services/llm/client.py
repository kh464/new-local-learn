from __future__ import annotations

import json

import httpx

from app.services.llm.config import RuntimeConfig


class ChatCompletionClient:
    def __init__(self, runtime_config: RuntimeConfig, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._runtime_config = runtime_config
        self._transport = transport

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
        payload = {
            "model": self._runtime_config.profile.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._runtime_config.provider.generation.temperature,
            "top_p": self._runtime_config.provider.generation.top_p,
            "max_tokens": self._runtime_config.provider.generation.max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._runtime_config.provider.api_key.get_secret_value()}"}

        last_error: Exception | None = None
        async with httpx.AsyncClient(
            base_url=self._runtime_config.provider.base_url.rstrip("/"),
            timeout=self._runtime_config.timeout_seconds,
            transport=self._transport,
        ) as client:
            for _ in range(self._runtime_config.max_retries + 1):
                try:
                    response = await client.post("/chat/completions", headers=headers, json=payload)
                    response.raise_for_status()
                    content = _extract_message_content(response.json())
                    return _load_json_content(content)
                except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    last_error = exc

        raise RuntimeError("LLM completion failed.") from last_error


def _extract_message_content(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM response does not contain choices.")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM response does not contain a message.")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "".join(parts)
    raise ValueError("LLM response content is not text.")


def _load_json_content(content: str) -> dict[str, object]:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.startswith("json"):
            normalized = normalized[4:]
        normalized = normalized.strip()
    parsed = json.loads(normalized)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object.")
    return parsed
