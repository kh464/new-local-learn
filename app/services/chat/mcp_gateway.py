from __future__ import annotations

from typing import Protocol

from app.services.chat.models import AgentObservation


class _McpSessionProtocol(Protocol):
    async def list_tools(self) -> list[dict[str, object]]: ...

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object: ...


class McpGateway:
    def __init__(self, *, session: _McpSessionProtocol) -> None:
        self._session = session

    async def list_tools(self) -> list[dict[str, object]]:
        tools = await self._session.list_tools()
        return tools if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: dict[str, object] | None = None) -> AgentObservation:
        normalized_arguments = arguments or {}
        try:
            raw = await self._session.call_tool(name, normalized_arguments)
        except Exception as exc:  # pragma: no cover - exercised by tests
            return AgentObservation(
                tool_name=name,
                success=False,
                summary=f"Tool call failed: {exc}",
                payload={"arguments": normalized_arguments},
            )
        return self._normalize_observation(name=name, raw=raw)

    def _normalize_observation(self, *, name: str, raw: object) -> AgentObservation:
        if isinstance(raw, AgentObservation):
            return raw

        if isinstance(raw, dict):
            if {"tool_name", "success", "summary"} <= set(raw):
                payload = raw.get("payload")
                if not isinstance(payload, dict):
                    raw = {
                        "tool_name": raw.get("tool_name") or name,
                        "success": bool(raw.get("success", False)),
                        "summary": str(raw.get("summary") or "").strip(),
                        "payload": {"result": payload},
                    }
                return AgentObservation.model_validate(raw)

            success = bool(raw.get("success", False))
            summary = str(raw.get("summary") or "").strip()
            payload = raw.get("payload")
            if not isinstance(payload, dict):
                payload = {"result": payload}
            return AgentObservation(
                tool_name=name,
                success=success,
                summary=summary or ("Tool call succeeded." if success else "Tool call failed."),
                payload=payload,
            )

        return AgentObservation(
            tool_name=name,
            success=True,
            summary="Tool call succeeded.",
            payload={"result": raw},
        )


McpToolGateway = McpGateway
