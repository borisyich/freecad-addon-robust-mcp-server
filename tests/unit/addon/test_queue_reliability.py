"""Tests for timeout cancellation in the FreeCAD-side execution queue."""

import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[3]
    / "freecad"
    / "RobustMCPBridge"
    / "freecad_mcp_bridge"
    / "server.py"
)
SPEC = importlib.util.spec_from_file_location("freecad_bridge_queue_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_cancelled_request_is_not_executed():
    plugin = MODULE.FreecadMCPPlugin(enable_xmlrpc=False)
    request = MODULE.ExecutionRequest(
        "raise RuntimeError('cancelled code must not run')",
        timeout_ms=1,
    )
    request.cancelled.set()
    plugin._request_queue.put(request)

    plugin._process_queue()

    assert request.completed.is_set()
    assert request.result is not None
    assert request.result["error_type"] == "CancelledError"
