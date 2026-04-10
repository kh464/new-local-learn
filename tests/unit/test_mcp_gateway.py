from __future__ import annotations

import pytest

from app.services.chat.mcp_gateway import McpGateway
from app.services.chat.models import AgentObservation


class _FakeSession:
    async def list_tools(self) -> list[dict[str, object]]:
        return [
            {
                "name": "search_code",
                "description": "Search code snippets from knowledge DB.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]

    async def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name == "explode":
            raise RuntimeError("boom")
        if name == "passthrough":
            return AgentObservation(
                tool_name="passthrough",
                success=True,
                summary="already normalized",
                payload={"ok": True},
            ).model_dump(mode="json")
        if name == "bad_payload":
            return {
                "tool_name": "bad_payload",
                "success": True,
                "summary": "broken payload",
                "payload": "not-a-dict",
            }
        return {"success": True, "summary": "tool executed", "payload": {"arguments": arguments}}


@pytest.mark.asyncio
async def test_mcp_gateway_lists_tools_from_session():
    gateway = McpGateway(session=_FakeSession())

    tools = await gateway.list_tools()

    assert len(tools) == 1
    assert tools[0]["name"] == "search_code"
    assert "inputSchema" in tools[0]


@pytest.mark.asyncio
async def test_mcp_gateway_normalizes_call_tool_results_and_errors():
    gateway = McpGateway(session=_FakeSession())

    success_observation = await gateway.call_tool("search_code", {"query": "health"})
    passthrough_observation = await gateway.call_tool("passthrough", {})
    bad_payload_observation = await gateway.call_tool("bad_payload", {})
    failure_observation = await gateway.call_tool("explode", {})

    assert isinstance(success_observation, AgentObservation)
    assert success_observation.tool_name == "search_code"
    assert success_observation.success is True
    assert success_observation.payload["arguments"]["query"] == "health"

    assert passthrough_observation.tool_name == "passthrough"
    assert passthrough_observation.success is True
    assert passthrough_observation.payload["ok"] is True

    assert bad_payload_observation.tool_name == "bad_payload"
    assert bad_payload_observation.success is True
    assert bad_payload_observation.payload["result"] == "not-a-dict"

    assert failure_observation.tool_name == "explode"
    assert failure_observation.success is False
    assert "boom" in failure_observation.summary
