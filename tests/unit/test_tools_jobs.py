"""Tests for session-local asynchronous MCP tool jobs."""

import asyncio

import pytest

from freecad_mcp.tools.jobs import register_job_tools


class _ToolManager:
    def __init__(self, tools):
        self._tools = tools

    def get_tool(self, name):
        return self._tools.get(name)


class _FakeMCP:
    def __init__(self):
        self.tools = {}
        self._tool_manager = _ToolManager(self.tools)
        self.release = asyncio.Event()

    def tool(self):
        def decorator(function):
            self.tools[function.__name__] = function
            return function

        return decorator

    async def call_tool(self, name, arguments):
        if name == "slow_tool":
            await self.release.wait()
            return {"value": arguments["value"]}
        raise ValueError(f"Unknown tool: {name}")


@pytest.mark.asyncio
async def test_background_job_returns_before_slow_tool_and_can_be_polled():
    mcp = _FakeMCP()
    mcp.tools["slow_tool"] = object()
    register_job_tools(mcp)

    started = await mcp.tools["start_tool_job"]("slow_tool", {"value": 7})
    assert started["state"] == "queued"

    for _ in range(3):
        await asyncio.sleep(0)
        running = await mcp.tools["get_tool_job"](started["job_id"])
        if running["state"] == "running":
            break
    assert running["state"] == "running"
    assert running["cancellable"] is False

    refused = await mcp.tools["cancel_tool_job"](started["job_id"])
    assert refused["state"] == "running"
    assert refused["cancel_requested"] is True
    assert refused["cancellable"] is False
    assert "cannot be interrupted safely" in refused["error"]

    mcp.release.set()
    await asyncio.sleep(0)
    completed = await mcp.tools["get_tool_job"](started["job_id"])
    assert completed["state"] == "completed"
    assert completed["result"] == {"value": 7}


@pytest.mark.asyncio
async def test_job_control_tools_cannot_recursively_submit_themselves():
    mcp = _FakeMCP()
    register_job_tools(mcp)

    with pytest.raises(ValueError, match="cannot be submitted"):
        await mcp.tools["start_tool_job"]("get_tool_job")


@pytest.mark.asyncio
async def test_queued_job_can_be_cancelled_before_wrapped_tool_starts():
    mcp = _FakeMCP()
    mcp.tools["slow_tool"] = object()
    register_job_tools(mcp)

    started = await mcp.tools["start_tool_job"]("slow_tool", {"value": 9})
    cancelled = await mcp.tools["cancel_tool_job"](started["job_id"])
    await asyncio.sleep(0)

    assert cancelled["state"] == "cancelled"
    assert cancelled["cancel_requested"] is True
    assert cancelled["cancellable"] is False
    polled = await mcp.tools["get_tool_job"](started["job_id"])
    assert polled["state"] == "cancelled"
