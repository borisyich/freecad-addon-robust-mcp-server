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


class _TimedOutMCP(_FakeMCP):
    async def call_tool(self, name, arguments):
        if name == "long_tool":
            raise ValueError(
                "TimeoutError: operation_state=running; continues_running=true; "
                "request_id=request-17"
            )
        return await super().call_tool(name, arguments)


class _RetainedBridge:
    def __init__(self):
        self.poll_count = 0

    async def get_execution_status(self, request_id):
        assert request_id == "request-17"
        self.poll_count += 1
        if self.poll_count == 1:
            return {
                "found": True,
                "request_id": request_id,
                "operation_state": "running",
                "continues_running": True,
            }
        return {
            "found": True,
            "request_id": request_id,
            "operation_state": "completed",
            "continues_running": False,
            "success": True,
            "result": {"value": 11},
        }


class _ErrorMCP(_FakeMCP):
    def __init__(self, outcome, *, raises=True):
        super().__init__()
        self.outcome = outcome
        self.raises = raises

    async def call_tool(self, name, arguments):
        if name != "error_tool":
            return await super().call_tool(name, arguments)
        if self.raises:
            raise ValueError(self.outcome)
        return self.outcome


class _MissingStatusBridge:
    async def get_execution_status(self, request_id):
        return {
            "found": False,
            "request_id": request_id,
            "operation_state": "unknown",
            "continues_running": None,
        }


class _UnknownStatusBridge:
    async def get_execution_status(self, request_id):
        return {
            "found": True,
            "request_id": request_id,
            "operation_state": "UNKNOWN",
            "continues_running": "unknown",
            # Some legacy transports use false for "no successful result yet".
            "success": False,
        }


class _StoppedStatusBridge:
    def __init__(self, operation_state):
        self.operation_state = operation_state

    async def get_execution_status(self, request_id):
        return {
            "found": True,
            "request_id": request_id,
            "operation_state": self.operation_state,
            "continues_running": False,
            "success": False,
        }


async def _wait_for_terminal(mcp, job_id):
    for _ in range(40):
        await asyncio.sleep(0.01)
        job = await mcp.tools["get_tool_job"](job_id)
        if job["state"] not in {
            "queued",
            "running",
            "freecad_running",
            "tracking_execution",
        }:
            return job
    raise AssertionError("job did not reach a terminal state")


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
    assert completed["isolation"] == "in_process"
    assert completed["hard_cancel_supported"] is False


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


@pytest.mark.asyncio
async def test_timed_out_freecad_execution_is_followed_to_real_completion():
    mcp = _TimedOutMCP()
    mcp.tools["long_tool"] = object()
    bridge = _RetainedBridge()

    async def get_bridge():
        return bridge

    register_job_tools(mcp, get_bridge)
    started = await mcp.tools["start_tool_job"]("long_tool", {"value": 11})

    for _ in range(40):
        await asyncio.sleep(0.05)
        polled = await mcp.tools["get_tool_job"](started["job_id"])
        if polled["state"] == "completed":
            break

    assert polled["state"] == "completed"
    assert polled["operation_state"] == "completed"
    assert polled["continues_running"] is False
    assert polled["freecad_busy"] is False
    assert polled["bridge_request_id"] == "request-17"
    assert polled["result_source"] == "retained_bridge_execution"
    assert polled["result"] == {"value": 11}
    assert bridge.poll_count >= 2


@pytest.mark.asyncio
@pytest.mark.parametrize("with_request_id", [True, False])
async def test_unknown_transport_timeout_is_not_classified_as_failure(
    with_request_id,
):
    request_text = "; request_id=legacy-4" if with_request_id else ""
    mcp = _ErrorMCP(
        "TimeoutError: operation_state=unknown; continues_running=unknown"
        + request_text
    )
    mcp.tools["error_tool"] = object()
    bridge = _MissingStatusBridge()

    async def get_bridge():
        return bridge

    register_job_tools(mcp, get_bridge)
    started = await mcp.tools["start_tool_job"]("error_tool")
    job = await _wait_for_terminal(mcp, started["job_id"])

    assert job["state"] == "unknown_after_timeout"
    assert job["operation_state"] == "unknown"
    assert job["continues_running"] is None
    assert job["timed_out"] is True
    assert job["termination_reason"] == "unknown_after_timeout"
    assert job["bridge_request_id"] == ("legacy-4" if with_request_id else None)


@pytest.mark.asyncio
async def test_queue_timeout_cancelled_before_start_is_not_failure():
    mcp = _ErrorMCP(
        {
            "isError": True,
            "structuredContent": {
                "error_type": "TimeoutError",
                "operation_state": "cancelled",
                "continues_running": False,
                "request_id": "queued-8",
            },
        },
        raises=False,
    )
    mcp.tools["error_tool"] = object()
    register_job_tools(mcp)

    started = await mcp.tools["start_tool_job"]("error_tool")
    job = await _wait_for_terminal(mcp, started["job_id"])

    assert job["state"] == "cancelled"
    assert job["operation_state"] == "cancelled"
    assert job["continues_running"] is False
    assert job["timed_out"] is True
    assert job["termination_reason"] == "timeout_before_start"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_state", ["cancelled", "not_started"])
async def test_equivalent_pre_start_timeout_states_are_cancelled(operation_state):
    mcp = _ErrorMCP(
        {
            "isError": True,
            "structuredContent": {
                "error_type": "TimeoutError",
                "operation_state": operation_state,
                "continues_running": False,
                "request_id": "queued-legacy",
            },
        },
        raises=False,
    )
    mcp.tools["error_tool"] = object()
    register_job_tools(mcp)

    started = await mcp.tools["start_tool_job"]("error_tool")
    job = await _wait_for_terminal(mcp, started["job_id"])

    assert job["state"] == "cancelled"
    assert job["operation_state"] == operation_state
    assert job["freecad_busy"] is False
    assert job["termination_reason"] == "timeout_before_start"


@pytest.mark.asyncio
async def test_non_timeout_not_started_rejection_remains_failure():
    mcp = _ErrorMCP(
        {
            "isError": True,
            "structuredContent": {
                "error_type": "ResourceLimitError",
                "operation_state": "not_started",
                "continues_running": False,
                "request_id": "rejected-1",
            },
        },
        raises=False,
    )
    mcp.tools["error_tool"] = object()
    register_job_tools(mcp)

    started = await mcp.tools["start_tool_job"]("error_tool")
    job = await _wait_for_terminal(mcp, started["job_id"])

    assert job["state"] == "failed"
    assert job["operation_state"] == "not_started"
    assert job["timed_out"] is False
    assert job["termination_reason"] == "tool_failure"


@pytest.mark.asyncio
async def test_unknown_retained_status_is_not_failure_even_with_success_false():
    mcp = _ErrorMCP(
        "TimeoutError: operation_state=unknown; continues_running=unknown; "
        "request_id=legacy-unknown"
    )
    mcp.tools["error_tool"] = object()
    bridge = _UnknownStatusBridge()

    async def get_bridge():
        return bridge

    register_job_tools(mcp, get_bridge)
    started = await mcp.tools["start_tool_job"]("error_tool")
    job = await _wait_for_terminal(mcp, started["job_id"])

    assert job["state"] == "unknown_after_timeout"
    assert job["operation_state"] == "unknown"
    assert job["continues_running"] is None
    assert job["freecad_busy"] is None
    assert job["termination_reason"] == "unknown_after_timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_state", "expected_job_state", "expected_reason"),
    [
        ("queued", "cancelled", "timeout_before_start"),
        ("running", "unknown_after_timeout", "unknown_after_timeout"),
    ],
)
async def test_retained_status_uses_execution_evidence_not_success_flag(
    status_state,
    expected_job_state,
    expected_reason,
):
    mcp = _ErrorMCP(
        "TimeoutError: operation_state=unknown; continues_running=unknown; "
        "request_id=legacy-state"
    )
    mcp.tools["error_tool"] = object()
    bridge = _StoppedStatusBridge(status_state)

    async def get_bridge():
        return bridge

    register_job_tools(mcp, get_bridge)
    started = await mcp.tools["start_tool_job"]("error_tool")
    job = await _wait_for_terminal(mcp, started["job_id"])

    assert job["state"] == expected_job_state
    assert job["operation_state"] == status_state
    assert job["continues_running"] is False
    assert job["freecad_busy"] is False
    assert job["termination_reason"] == expected_reason


@pytest.mark.asyncio
async def test_ordinary_tool_error_remains_failure():
    mcp = _ErrorMCP("invalid modeling parameter")
    mcp.tools["error_tool"] = object()
    register_job_tools(mcp)

    started = await mcp.tools["start_tool_job"]("error_tool")
    job = await _wait_for_terminal(mcp, started["job_id"])

    assert job["state"] == "failed"
    assert job["timed_out"] is False
    assert job["termination_reason"] == "tool_failure"
