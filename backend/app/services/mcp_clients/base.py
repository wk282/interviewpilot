from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from typing import Any


class MCPToolError(RuntimeError):
    """Raised when an MCP transport or tool invocation cannot be completed."""


async def call_mcp_tool(
    *,
    server_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Call one Streamable HTTP MCP tool and normalize its structured result."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as error:  # pragma: no cover - exercised in minimal installs
        raise MCPToolError("Python MCP SDK is not installed") from error

    async def invoke() -> dict[str, Any]:
        async with AsyncExitStack() as stack:
            streams = await stack.enter_async_context(
                streamable_http_client(server_url)
            )
            read_stream, write_stream = streams[0], streams[1]
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            if result.isError:
                messages = [
                    getattr(item, "text", "")
                    for item in result.content
                    if getattr(item, "text", "")
                ]
                raise MCPToolError("; ".join(messages) or f"MCP tool {tool_name} failed")

            structured = getattr(result, "structuredContent", None)
            if isinstance(structured, dict):
                return structured
            for item in result.content:
                text = getattr(item, "text", None)
                if not text:
                    continue
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            raise MCPToolError(f"MCP tool {tool_name} returned no JSON object")

    try:
        return await asyncio.wait_for(invoke(), timeout=timeout_seconds)
    except MCPToolError:
        raise
    except Exception as error:
        raise MCPToolError(
            f"{tool_name} call failed: {type(error).__name__}: {error}"
        ) from error
