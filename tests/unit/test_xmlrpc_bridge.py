"""Tests for XML-RPC transport and GUI queue health checks."""

import xmlrpc.client
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from freecad_mcp.bridge.base import ExecutionResult
from freecad_mcp.bridge.xmlrpc import XmlRpcBridge


@pytest.mark.asyncio
async def test_ping_uses_lightweight_xmlrpc_method():
    bridge = XmlRpcBridge()
    bridge._proxy = MagicMock()
    bridge._call_rpc = AsyncMock(return_value={"pong": True})

    latency = await bridge.ping()

    assert latency >= 0
    bridge._call_rpc.assert_awaited_once_with("ping", timeout=5.0)


@pytest.mark.asyncio
async def test_connect_requires_transport_and_queue_health():
    bridge = XmlRpcBridge()
    bridge.ping = AsyncMock(return_value=1.0)
    bridge.check_execution_queue = AsyncMock(return_value=2.0)

    with patch("xmlrpc.client.ServerProxy", return_value=MagicMock()):
        await bridge.connect()

    assert bridge._connected is True
    bridge.ping.assert_awaited_once()
    bridge.check_execution_queue.assert_awaited_once_with(5000)


@pytest.mark.asyncio
async def test_queue_health_failure_has_actionable_error():
    bridge = XmlRpcBridge()
    bridge._proxy = MagicMock()
    bridge.execute_python = AsyncMock(
        return_value=ExecutionResult(
            success=False,
            result=None,
            stdout="",
            stderr="Execution timed out after 5000ms",
            execution_time_ms=5000,
            error_type="TimeoutError",
        )
    )

    with pytest.raises(ConnectionError, match="Restart 'MCP Bridge' inside FreeCAD"):
        await bridge.check_execution_queue(5000)


@pytest.mark.asyncio
async def test_execute_falls_back_to_legacy_method():
    bridge = XmlRpcBridge()
    bridge._proxy = MagicMock()
    bridge._call_rpc = AsyncMock(
        side_effect=[
            xmlrpc.client.Fault(
                1,
                'method "execute_with_timeout" is not supported',
            ),
            {
                "success": True,
                "result": 42,
                "stdout": "",
                "stderr": "",
            },
        ]
    )

    result = await bridge.execute_python("_result_ = 42", timeout_ms=2000)

    assert result.success is True
    assert result.result == 42
    assert bridge._call_rpc.await_count == 2
    assert bridge._call_rpc.await_args_list[0].args[:3] == (
        "execute_with_timeout",
        "_result_ = 42",
        2000,
    )
    assert bridge._call_rpc.await_args_list[1].args[:2] == (
        "execute",
        "_result_ = 42",
    )
